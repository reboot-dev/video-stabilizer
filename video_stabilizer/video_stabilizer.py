import time
import cv2
import threading
from video_stabilizer_clients.stabilize_client import StabilizeClient
import video_stabilizer_server.stabilize_server as stabilizer_server
import video_stabilizer_server.cumsum_server as cumsum_server 
import video_stabilizer_server.flow_server as flow_server 
import video_stabilizer_proto.video_stabilizer_pb2_grpc as pb2_grpc
import video_stabilizer_proto.video_stabilizer_pb2 as pb2
import numpy as np
from collections import defaultdict


class Writer:
    def __init__(self, video_pathname):
        # TODO: need to change this to be a different video pathname, let's use "stabilized_" + video_pathname
        self.video_pathname = video_pathname
        self.v = cv2.VideoCapture(video_pathname)

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

        # Write the frame to the file
        frame_out = cv2.hconcat([frame, frame_stabilized])

        ## If the image is too big, resize it.
        if(frame_out.shape[1] > 1920): 
            frame_out = cv2.resize(frame_out, (frame_out.shape[1]//2, frame_out.shape[0]//2));
        
        # cv2.imshow("Before and After", frame_out)
        # cv2.waitKey(1)
        out.write(frame_out)


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


def np_array_encode(lst):
    return np.ndarray.tobytes(lst)

def np_array_decode(b):
    return np.frombuffer(b)

def process_videos(video_pathname, num_videos, output_filename):
    # Initializing signal
    # signal = Signal()

    # Initializing viewer
    # viewer = Viewer(video_pathname)

    # Initializing a sink
    # sink = Sink(signal, viewer)

    video_in = cv2.VideoCapture(video_pathname)
    num_total_frames = int(video_in.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = int(video_in.get(cv2.CAP_PROP_FPS))    
    print("Processing total frames", num_total_frames, "from video", video_pathname)
   
    decoder = Decoder(video_pathname, 0)
    start_frame = 0

    radius = fps

    # Start of what would be process_chunk()
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
    trajectory = []
    transforms = []

    # 3D array
    features = np.empty(0)

    frame_timestamp = start_frame / fps
    diff = frame_timestamp - time.time()
    if diff > 0:
        time.sleep(diff)
    frame_timestamps.append(frame_timestamp)
    prev_frame = decoder.decode(start_frame)

    stabilize_client = StabilizeClient()
    for frame_index in range(start_frame, num_total_frames - 1):
        frame_timestamp = (start_frame + frame_index + 1) / fps
        diff = frame_timestamp - time.time()
        if diff > 0:
            time.sleep(diff)
        frame_timestamps.append(frame_timestamp)

        frame = decoder.decode(start_frame + frame_index + 1)

        print(prev_frame)
        response = stabilize_client.stabilize(pb2.StabilizeRequest(frame_image=np_array_encode(frame), prev_frame=np_array_encode(prev_frame), features=np_array_encode(features), trajectory=list_encode(trajectory), padding=padding, transforms=list_encode(transforms), frame_index=frame_index))

        prev_frame = response.stabilized_frame_image
        features = pickle.loads(response.features)
        trajectory = pickle.loads(response.trajectory)
        transforms = pickle.loads(response.transforms)

        writer.write_stabilized_video_frame_out(response.transforms?   response.stabilized_frame_image?)

    # TODO: Should we be calling smooth here?
    # while next_to_send < num_total_frames - 1:
    #     trajectory.append(trajectory[-1])
    #     midpoint = radius
    #     final_transform = smooth.options(resources={
    #         resource: 0.001
    #         }).remote(transforms.pop(0), trajectory[midpoint], *trajectory)
    #     trajectory.pop(0)

    #     final = sink.send.remote(next_to_send, final_transform,
    #             frame_timestamps.pop(0))
    #     next_to_send += 1


    # Wait for all video frames to complete
    # ready = 0
    # while ready != num_videos:
    #     time.sleep(1)
    #     ready = ray.get(signal.wait.remote())

    # latencies = []
    # for sink in sinks:
    #     latencies += ray.get(sink.latencies.remote())
    # if output_filename:
    #     with open(output_filename, 'w') as f:
    #         for t, l in latencies:
    #             f.write("{} {}\n".format(t, l))
    # else:
    #     for latency in latencies:
    #         print(latency)
    # latencies = [l for _, l in latencies]
    # print("Mean latency:", np.mean(latencies))
    # print("Max latency:", np.max(latencies))


def main(args):
    threading.Thread(target=stabilizer_server.serve).start()
    threading.Thread(target=flow_server.serve).start()
    threading.Thread(target=cumsum_server.serve).start()
    process_videos(args.video_path, args.num_videos, args.output_file)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run the video stabilizer.")

    parser.add_argument("--num-videos", required=True, type=int)
    parser.add_argument("--video-path", required=True, type=str)
    parser.add_argument("--output-file", type=str)
    inputs = parser.parse_args()
    main(inputs)
    