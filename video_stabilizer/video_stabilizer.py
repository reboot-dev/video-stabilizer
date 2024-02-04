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

def fixBorder(frame):
  s = frame.shape
  # Scale the image 4% without moving the center
  T = cv2.getRotationMatrix2D((s[1]/2, s[0]/2), 0, 1.04)
  frame = cv2.warpAffine(frame, T, (s[1], s[0]))
  return frame

class Writer:
    def __init__(self, video_pathname, video_capture, video_writer):
        # TODO: need to change this to be a different video pathname, let's use "stabilized_" + video_pathname
        # self.video_pathname = video_pathname
        # self.v = cv2.VideoCapture(video_pathname)
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

        # Write the frame to the file
        # frame_out = cv2.hconcat([frame, frame_stabilized])

        ## If the image is too big, resize it.
        # if(frame_out.shape[1] > 1920): 
        #     frame_out = cv2.resize(frame_out, (frame_out.shape[1]//2, frame_out.shape[0]//2));
        
        # cv2.imshow("Before and After", frame_out)
        # cv2.waitKey(1)
        # out.write(frame_out)


class Decoder:
    def __init__(self, filename, start_frame):
        self.v = cv2.VideoCapture(filename)
        self.v.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

    def decode(self, frame):
        if frame != self.v.get(cv2.CAP_PROP_POS_FRAMES):
            print("next frame", frame, ", at frame", self.v.get(cv2.CAP_PROP_POS_FRAMES))
            self.v.set(cv2.CAP_PROP_POS_FRAMES, frame)
        grabbed, frame = self.v.read()
        if not grabbed:
            return None
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) 
        return frame

    def ready(self):
        return
        
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

    # Set up Writer instance
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    # fps = int(video_in.get(cv2.CAP_PROP_FPS))
    width = int(video_in.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(video_in.get(cv2.CAP_PROP_FRAME_HEIGHT))
    video_writer = cv2.VideoWriter("/workspaces/video-stabilizer/stabilized_video/video.mp4", fourcc,
                     fps, (width, height))
    writer = Writer("/workspaces/video-stabilizer/stabilized_video/video.mp4", video_in, video_writer)
   
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

    count = 0

    stabilize_client = StabilizeClient()
    for frame_index in range(start_frame, num_total_frames - 1):
        frame_timestamp = (start_frame + frame_index + 1) / fps
        diff = frame_timestamp - time.time()
        if diff > 0:
            time.sleep(diff)
        frame_timestamps.append(frame_timestamp)

        frame = decoder.decode(start_frame + frame_index + 1)

        if frame is None:
            break

        print(count)
        count = count + 1

        stabilize_response = stabilize_client.stabilize(pb2.StabilizeRequest(frame_image=pickle.dumps(frame), prev_frame=pickle.dumps(prev_frame), features=pickle.dumps(features), trajectory=pickle.dumps(trajectory), padding=padding, transforms=pickle.dumps(transforms), frame_index=frame_index, radius=radius, next_to_send=next_to_send))

        final_transform = pickle.loads(stabilize_response.final_transform)
        features = pickle.loads(stabilize_response.features)
        trajectory = pickle.loads(stabilize_response.trajectory)
        transforms = pickle.loads(stabilize_response.transforms)
        next_to_send = stabilize_response.next_to_send

        if final_transform is not None:
            writer.write_stabilized_video_frame_out(final_transform)

    smooth_client = SmoothClient()
    while next_to_send < num_total_frames - 1:
        trajectory.append(trajectory[-1])
        midpoint = radius

        if len(transforms) == 0:
            break

        smooth_response = smooth_client.smooth(pb2.SmoothRequest(transforms_element=pickle.dumps(transforms.pop(0)), trajectory_element=pickle.dumps(trajectory[midpoint]), trajectory=pickle.dumps(trajectory)))
        final_transform = pickle.loads(smooth_response.final_transform)
        trajectory.pop(0)

        writer.write_stabilized_video_frame_out(final_transform)
        next_to_send += 1

    print("finished stabilizing")

def main(args):
    # threading.Thread(target=stabilizer_server.serve).start()
    # threading.Thread(target=flow_server.serve).start()
    # threading.Thread(target=cumsum_server.serve).start()
    # threading.Thread(target=smooth_server.serve).start()
    process_videos(args.video_path, args.num_videos, args.output_file)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run the video stabilizer.")

    parser.add_argument("--num-videos", required=True, type=int)
    parser.add_argument("--video-path", required=True, type=str)
    parser.add_argument("--output-file", type=str)
    inputs = parser.parse_args()
    main(inputs)
    