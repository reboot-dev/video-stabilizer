import time
import cv2
import threading
from video_stabilizer_clients.stabilize_client import StabilizeClient
from video_stabilizer_clients.smooth_client import SmoothClient
import video_stabilizer_server.stabilize_server as stabilizer_server
import video_stabilizer_server.cumsum_server as cumsum_server 
import video_stabilizer_server.flow_server as flow_server 
import video_stabilizer_server.smooth_server as smooth_server 
import video_stabilizer_proto.video_stabilizer_pb2_grpc as pb2_grpc
import video_stabilizer_proto.video_stabilizer_pb2 as pb2
import numpy as np
from collections import defaultdict
import pickle5 as pickle
import time

class Signal:
    def __init__(self):
        self.num_signals = 0

    def send(self):
        self.num_signals += 1

    def wait(self):
        return self.num_signals

    def ready(self):
        return


class Decoder:
    def __init__(self, filename, start_frame):
        self.v = cv2.VideoCapture(filename)
        self.v.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

    def decode(self, frame):
        if frame != self.v.get(cv2.CAP_PROP_POS_FRAMES):
            print("next frame", frame, ", at frame", self.v.get(cv2.CAP_PROP_POS_FRAMES))
            self.v.set(cv2.CAP_PROP_POS_FRAMES, frame)
        grabbed, frame = self.v.read()
        assert grabbed
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) 
        return frame

    def ready(self):
        return


def fixBorder(frame):
  s = frame.shape
  # Scale the image 4% without moving the center
  T = cv2.getRotationMatrix2D((s[1]/2, s[0]/2), 0, 1.04)
  frame = cv2.warpAffine(frame, T, (s[1], s[0]))
  return frame

class Writer:
    def __init__(self, output_filename, video_capture, video_writer):
        self.output_filename = output_filename
        self.v = video_capture
        self.w = video_writer

    def write_stabilized_video_frame_out(self, transform):
        success, frame = self.v.read() 
        assert success

        # Extract transformations from the new transformation array
        dx, dy, da = transform

        # Reconstruct transformation matrix accordingly to new values
        m = np.zeros((2,3), np.float32)
        m[0,0] = np.cos(da)
        m[0,1] = -np.sin(da)
        m[1,0] = np.sin(da)
        m[1,1] = np.cos(da)
        m[0,2] = dx
        m[1,2] = dy

        # Apply affine wrapping to the given frame
        w = int(self.v.get(cv2.CAP_PROP_FRAME_WIDTH)) 
        h = int(self.v.get(cv2.CAP_PROP_FRAME_HEIGHT))
        frame_stabilized = cv2.warpAffine(frame, m, (w,h))

        # Fix border artifacts
        frame_stabilized = fixBorder(frame_stabilized) 
        
        # Write the stabilized frame
        self.w.write(frame_stabilized)

    def ready(self):
        return



class Sink:
    def __init__(self, signal, writer):
        self.signal = signal
        self.num_frames_left = {}
        self.latencies = defaultdict(list)

        self.writer = writer
        self.last_view = None

    def set_expected_frames(self, video_index, num_frames):
        self.num_frames_left[video_index] = num_frames
        print("Expecting", self.num_frames_left[video_index], "total frames from video", video_index)

    def send(self, video_index, frame_index, transform, timestamp):
        if frame_index < len(self.latencies[video_index]):
            return
        assert frame_index == len(self.latencies[video_index]), frame_index

        self.latencies[video_index].append(time.time() - timestamp)

        self.num_frames_left[video_index] -= 1
        if self.num_frames_left[video_index] % 100 == 0:
            print("Expecting", self.num_frames_left[video_index], "more frames from video", video_index)

        if self.num_frames_left[video_index] == 0:
            print("Video {} DONE".format(video_index))
            if self.last_view is not None:
                self.last_view
            self.signal.send()

        if self.writer is not None and video_index == 0:
            self.last_view = self.writer.write_stabilized_video_frame_out(transform)

    def latencies(self):
        latencies = []
        for video in self.latencies.values():
            for i, l in enumerate(video):
                latencies.append((i, l))
        return latencies

    def ready(self):
        return
    


def process_chunk(video_index, video_pathname, sink, num_frames, fps, start_timestamp):
    decoder = Decoder(video_pathname, 0)

    start_frame = 0
    radius = fps
    trajectory = []

    # Start at `radius` before the start frame, since we need to compute a
    # moving average.
    next_to_send = start_frame
    start_frame -= radius
    if start_frame < 0:
        padding = start_frame * -1
        start_frame = 0
    else:
        padding = 0

    frame_timestamps = []
    transforms = []
    # 3D array
    features = np.empty(0)

    frame_timestamp = start_timestamp + start_frame / fps
    diff = frame_timestamp - time.time()
    if diff > 0:
        time.sleep(diff)
    frame_timestamps.append(frame_timestamp)
    prev_frame = decoder.decode(start_frame)

    stabilize_client = StabilizeClient()
    for frame_index in range(start_frame, num_frames - 1):
        frame_timestamp = start_timestamp + (start_frame + frame_index + 1) / fps
        diff = frame_timestamp - time.time()
        if diff > 0:
            time.sleep(diff)
        frame_timestamps.append(frame_timestamp)

        frame = decoder.decode(start_frame + frame_index + 1)

        stabilize_response = stabilize_client.stabilize(pb2.StabilizeRequest(frame_image=pickle.dumps(frame), prev_frame=pickle.dumps(prev_frame), features=pickle.dumps(features), trajectory=pickle.dumps(trajectory), padding=padding, transforms=pickle.dumps(transforms), frame_index=frame_index, radius=radius))
        prev_frame = frame

        final_transform = pickle.loads(stabilize_response.final_transform)
        features = pickle.loads(stabilize_response.features)
        trajectory = pickle.loads(stabilize_response.trajectory)
        transforms = pickle.loads(stabilize_response.transforms)

        if final_transform is not None:
            sink.send(video_index, next_to_send, final_transform, frame_timestamps.pop(0))
            next_to_send += 1

    smooth_client = SmoothClient()
    while next_to_send < num_frames - 1:
        trajectory.append(trajectory[-1])
        midpoint = radius

        smooth_response = smooth_client.smooth(pb2.SmoothRequest(transforms_element=pickle.dumps(transforms.pop(0)), trajectory_element=pickle.dumps(trajectory[midpoint]), trajectory=pickle.dumps(trajectory)))
        final_transform = pickle.loads(smooth_response.final_transform)
        trajectory.pop(0)

        final = sink.send(video_index, next_to_send, final_transform, frame_timestamps.pop(0))
        next_to_send += 1

    print("finished stabilizing")
    return final
        


def process_videos(video_pathname, num_videos, output_filename, max_frames, num_sinks, offset_seconds):
    signal = Signal()
    signal.ready()

    video_in = cv2.VideoCapture(video_pathname)
    fps = int(video_in.get(cv2.CAP_PROP_FPS))    
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    width = int(video_in.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(video_in.get(cv2.CAP_PROP_FRAME_HEIGHT))
    video_writer = cv2.VideoWriter(output_filename, fourcc,
                     fps, (width, height))

    writer = Writer(output_filename, video_in, video_writer)
    writer.ready()

    sinks = [Sink(signal, writer) for i in range(num_sinks)]
    [sink.ready() for sink in sinks]

    v = cv2.VideoCapture(video_pathname)
    num_total_frames = int(min(v.get(cv2.CAP_PROP_FRAME_COUNT), max_frames))
    fps = int(v.get(cv2.CAP_PROP_FPS))
    print("Processing total frames", num_total_frames, "from video", video_pathname)
    for i in range(num_videos):
        sinks[i % len(sinks)].set_expected_frames(i, num_total_frames - 1)

    # Give the actors some time to start up.
    start_timestamp = time.time() + offset_seconds

    for i in range(num_videos):
        process_chunk(i, video_pathname, sinks[i % len(sinks)], num_total_frames, fps, start_timestamp)

    # Wait for all video frames to complete. It is okay to poll this actor
    # because it is not on the critical path of video processing latency.
    # ready = 0
    # while ready != num_videos:
    #     time.sleep(1)
    #     ready = signal.wait()

def main(args):
    num_sinks = args.num_videos // args.max_videos_per_sink

    offset_seconds = 5
    process_videos(args.video_path, args.num_videos, args.output_file, args.max_frames, num_sinks, offset_seconds)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run the video stabilizer.")

    parser.add_argument("--num-videos", required=True, type=int)
    parser.add_argument("--video-path", required=True, type=str)
    parser.add_argument("--output-file", required=True, type=str)
    parser.add_argument("--max-frames", default=600, type=int)
    # Limit the number of videos that can send to one sink.
    parser.add_argument("--max-videos-per-sink", default=9, type=int)
    inputs = parser.parse_args()
    main(inputs)
    