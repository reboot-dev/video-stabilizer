import time
import cv2
import threading
from video_stabilizer_wrappers.stabilizer import Stabilizer
from video_stabilizer_wrappers.smooth import Smooth
import video_stabilizer_server.stabilize_server as stabilizer_server
import video_stabilizer_server.cumsum_server as cumsum_server 
import video_stabilizer_server.flow_server as flow_server 
import video_stabilizer_server.smooth_server as smooth_server 
import video_stabilizer_proto.video_stabilizer_pb2_grpc as pb2_grpc
import video_stabilizer_proto.video_stabilizer_pb2 as pb2
import numpy as np
from collections import defaultdict
import pickle5 as pickle
import sys
from minio import Minio
from io import BytesIO


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
        self.client = Minio('play.min.io',
               access_key='Q3AM3UQ867SPQQA43P2F',
               secret_key='zuf+tfteSlswRu7BJ86wekitnifILbZam1KYY3TG',
               secure=True)

    def write_stabilized_video_frame_out(self, transform, process_mode):
        success, frame = self.v.read() 
        assert success
        print(len(frame.tobytes()))

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
        
        if process_mode == 0:
        # Write the stabilized frame
            self.w.write(frame_stabilized)
        else:
            # Create a BytesIO object to hold the frame data
            # bytes_io = BytesIO()

            
            # Write the frame data to the BytesIO object
            bytes = frame_stabilized.tobytes()

            bytes_io = BytesIO(bytes)
            # bytes_io.write(bytes)
            

            # Set the BytesIO object's position to the beginning
            # bytes_io.seek(0)

            # create minio bucket
            found = self.client.bucket_exists("respect")
            if not found:
                self.client.make_bucket("respect")

            # Upload the frame to MinIO as a new object in respect bucket
            # length=bytes_io.getbuffer().nbytes
            self.client.put_object(bucket_name='respect', object_name=f'frame_{self.v.get(cv2.CAP_PROP_POS_FRAMES)}', data=bytes_io, length=len(bytes))



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
            return []
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) 
        return frame

    def ready(self):
        return
        
def process_videos(video_pathname, num_videos, output_filename,process_mode):
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

    stabilizer = Stabilizer(process_mode)
    for frame_index in range(start_frame, num_total_frames - 1):
        frame_timestamp = (start_frame + frame_index + 1) / fps
        diff = frame_timestamp - time.time()
        if diff > 0:
            time.sleep(diff)
        frame_timestamps.append(frame_timestamp)

        frame = decoder.decode(start_frame + frame_index + 1)

        if frame == []:
            break

        # print(count)
        count = count + 1

        (final_transform,features,trajectory,transforms,next_to_send) = stabilizer.stabilize(frame_image=frame, prev_frame=prev_frame, features=features, trajectory=trajectory, padding=padding, transforms=transforms, frame_index=frame_index, radius=radius, next_to_send=next_to_send)

        # print(f"stab response size {sys.getsizeof(stabilize_response)}")
        # print(sys.getsizeof(final_transform))
        # print(sys.getsizeof(trajectory))
        # print(sys.getsizeof(transforms))
        # print(sys.getsizeof(next_to_send))

        if final_transform != []:
            writer.write_stabilized_video_frame_out(final_transform,process_mode)

    smooth = Smooth()
    while next_to_send < num_total_frames - 1:
        trajectory.append(trajectory[-1])
        midpoint = radius

        if len(transforms) == 0:
            break

        final_transform = smooth.smooth(transforms_element=transforms.pop(0), trajectory_element=trajectory[midpoint], trajectory=trajectory)
        trajectory.pop(0)

        writer.write_stabilized_video_frame_out(final_transform)
        next_to_send += 1

    # Release the capture and writer objects
    video_in.release()
    video_writer.release()

    # Close all windows
    cv2.destroyAllWindows()
    print("finished stabilizing")

def main(args):
    threading.Thread(target=stabilizer_server.serve).start()
    threading.Thread(target=flow_server.serve).start()
    threading.Thread(target=cumsum_server.serve).start()
    threading.Thread(target=smooth_server.serve).start()
    process_videos(args.video_path, args.num_videos, args.output_file,args.process_mode)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run the video stabilizer.")

    parser.add_argument("--num-videos", required=True, type=int)
    parser.add_argument("--video-path", required=True, type=str)
    parser.add_argument("--output-file", type=str)
    parser.add_argument("--process-mode", required=True,type=int)
    inputs = parser.parse_args()
    main(inputs)
    