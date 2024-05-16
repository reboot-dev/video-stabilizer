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
import io
import json
import boto3
import os

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

def construct_stabilize_request(frame, prev_frame, features, trajectory, padding, transforms, frame_index, radius, process_mode, s3_client, bucket_name):
    if process_mode == 0:
        frame_image_bytes = pickle.dumps(frame)
        prev_frame_bytes = pickle.dumps(prev_frame)
        features_bytes = pickle.dumps(features)
        trajectory_bytes = pickle.dumps(trajectory)
        transforms_bytes = pickle.dumps(transforms)

        stabilize_request_frame_data = pb2.StabilizeRequestFrameData(
            frame_image=frame_image_bytes,
            prev_frame=prev_frame_bytes,
            features=features_bytes,
            trajectory=trajectory_bytes,
            padding=padding,
            transforms=transforms_bytes,
            frame_index=frame_index,
            radius=radius
        )

        stabilize_request = pb2.StabilizeRequest(
            stabilize_frame_data=stabilize_request_frame_data,
            process_mode=process_mode
        )

        return stabilize_request
    elif process_mode == 1:
        stabilize_request_data = {
            "frame_image": pickle.dumps(frame).decode('latin1'),
            "prev_frame": pickle.dumps(prev_frame).decode('latin1'),
            "features": pickle.dumps(features).decode('latin1'),
            "trajectory": trajectory,
            "padding": padding,
            "transforms": transforms,
            "frame_index": frame_index,
            "radius": radius
        }

        stabilize_request_json_data = json.dumps(stabilize_request_data)
        stabilize_request_json_data_bytes = stabilize_request_json_data.encode("utf-8")
        stabilize_request_json_data_file = io.BytesIO(stabilize_request_json_data_bytes)

        # NOTE: MinIO Code
        # minio_client.put_object(bucket_name, "stabilize_request_json", stabilize_request_json_data_file, len(stabilize_request_json_data_bytes))
        # stabilize_request_json_url = minio_client.get_presigned_url("GET", bucket_name, "stabilize_request_json")

        key = "stabilize_request_json"
        s3_client.put_object(Bucket=bucket_name, Key=key, Body=stabilize_request_json_data_file)

        stabilize_request = pb2.StabilizeRequest(
            stabilize_request_json_key=key,
            process_mode=process_mode
        )
        return stabilize_request

def extract_stabilize_response(process_mode, stabilize_response, s3_client, bucket_name):
    if process_mode == 0:
        final_transform = pickle.loads(stabilize_response.stabilize_frame_data.final_transform)
        features = pickle.loads(stabilize_response.stabilize_frame_data.features)
        trajectory = pickle.loads(stabilize_response.stabilize_frame_data.trajectory)
        transforms = pickle.loads(stabilize_response.stabilize_frame_data.transforms)
    elif process_mode == 1:
        stabilize_response_json_data = s3_client.get_object(Bucket=bucket_name, Key=stabilize_response.stabilize_response_json_key)['Body'].read().decode("utf-8")
        stabilize_response_data = json.loads(stabilize_response_json_data)
        final_transform = pickle.loads(stabilize_response_data["final_transform"].encode('latin1'))
        features = pickle.loads(stabilize_response_data["features"].encode('latin1'))
        trajectory = stabilize_response_data["trajectory"]
        transforms = stabilize_response_data["transforms"]
    return final_transform, features, trajectory, transforms

def construct_smooth_request(transforms_element, trajectory_element, trajectory, process_mode, s3_client, bucket_name):
    if process_mode == 0:
        transforms_element_bytes = pickle.dumps(transforms_element)
        trajectory_element_bytes = pickle.dumps(trajectory_element)
        trajectory_bytes = pickle.dumps(trajectory)

        smooth_request_frame_data = pb2.SmoothRequestFrameData(
            transforms_element=transforms_element_bytes,
            trajectory_element=trajectory_element_bytes,
            trajectory=trajectory_bytes
        )

        smooth_request = pb2.SmoothRequest(smooth_frame_data=smooth_request_frame_data, process_mode=process_mode)
    elif process_mode == 1:
        smooth_request_data = {
            "transforms_element": transforms_element,
            "trajectory_element": trajectory_element,
            "trajectory": trajectory
        }

        smooth_request_json_data = json.dumps(smooth_request_data)
        smooth_request_json_data_bytes = smooth_request_json_data.encode("utf-8")
        smooth_request_json_data_file = io.BytesIO(smooth_request_json_data_bytes)

        # NOTE: MinIO Code
        # minio_client.put_object(bucket_name, "smooth_request_json", smooth_request_json_data_file, len(smooth_request_json_data_bytes))
        # smooth_request_json_url = minio_client.get_presigned_url("GET", bucket_name, "smooth_request_json")

        key = "smooth_request_json"
        s3_client.put_object(Bucket=bucket_name, Key=key, Body=smooth_request_json_data_file)
        smooth_request = pb2.SmoothRequest(smooth_request_json_key=key, process_mode=process_mode)
    return smooth_request

def extract_smooth_response(smooth_response, process_mode, s3_client, bucket_name):
    if process_mode == 0:
        final_transform = pickle.loads(smooth_response.final_transform)
    elif process_mode == 1:
        smooth_response_json_data = s3_client.get_object(Bucket=bucket_name, Key=smooth_response.smooth_response_json_key)['Body'].read().decode("utf-8")
        smooth_response_data = json.loads(smooth_response_json_data)
        final_transform = pickle.loads(smooth_response_data["final_transform"].encode('latin1'))
    return final_transform

def process_chunk(video_index, video_pathname, sink, num_frames, fps, start_timestamp, process_mode):
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

    # Initialize MinIO client if process_mode == 1
    if process_mode == 1:
        # NOTE: MinIO Code
        # minio_client = Minio(
        #     "play.min.io",
        #     access_key="Q3AM3UQ867SPQQA43P2F",
        #     secret_key="zuf+tfteSlswRu7BJ86wekitnifILbZam1KYY3TG",
        # )

        # bucket_name = "video-stabilizer"
        # found = minio_client.bucket_exists(bucket_name)
        # if not found:
        #     minio_client.make_bucket(bucket_name)

        aws_access_key_id = os.environ["AWS_ACCESS_KEY_ID"]
        aws_secret_access_key = os.environ["AWS_SECRET_ACCESS_KEY"]
        s3_client = boto3.client('s3', aws_access_key_id=aws_access_key_id, aws_secret_access_key=aws_secret_access_key)
        bucket_name = "respect-dev-1"
    else:
        # NOTE: MinIO Code
        # minio_client = None
        # bucket_name = None

        s3_client = None
        bucket_name = None

    stabilize_client = StabilizeClient()
    for frame_index in range(start_frame, num_frames - 1):
        frame_timestamp = start_timestamp + (start_frame + frame_index + 1) / fps
        diff = frame_timestamp - time.time()
        if diff > 0:
            time.sleep(diff)
        frame_timestamps.append(frame_timestamp)

        frame = decoder.decode(start_frame + frame_index + 1)

        stabilize_request = construct_stabilize_request(frame, prev_frame, features, trajectory, padding, transforms, frame_index, radius, process_mode, s3_client, bucket_name)
        stabilize_response = stabilize_client.stabilize(stabilize_request)
        prev_frame = frame

        final_transform, features, trajectory, transforms = extract_stabilize_response(process_mode, stabilize_response, s3_client, bucket_name)

        if final_transform is not None:
            sink.send(video_index, next_to_send, final_transform, frame_timestamps.pop(0))
            next_to_send += 1

    print("still stabilizing")
    
    smooth_client = SmoothClient()
    while next_to_send < num_frames - 1:
        trajectory.append(trajectory[-1])
        midpoint = radius

        smooth_request = construct_smooth_request(transforms.pop(0), trajectory[midpoint], trajectory, process_mode, s3_client, bucket_name)
        smooth_response = smooth_client.smooth(smooth_request)
        final_transform = extract_smooth_response(smooth_response, process_mode, s3_client, bucket_name)
        trajectory.pop(0)

        final = sink.send(video_index, next_to_send, final_transform, frame_timestamps.pop(0))
        next_to_send += 1

    print("finished stabilizing")
    return final
        


def process_videos(video_pathname, num_videos, output_filename, max_frames, num_sinks, offset_seconds, process_mode):
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
        process_chunk(i, video_pathname, sinks[i % len(sinks)], num_total_frames, fps, start_timestamp, process_mode)

    # Wait for all video frames to complete. It is okay to poll this actor
    # because it is not on the critical path of video processing latency.
    # ready = 0
    # while ready != num_videos:
    #     time.sleep(1)
    #     ready = signal.wait()

def main(args):
    num_sinks = args.num_videos // args.max_videos_per_sink

    offset_seconds = 5
    process_videos(args.video_path, args.num_videos, args.output_file, args.max_frames, num_sinks, offset_seconds, args.process_mode)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run the video stabilizer.")

    parser.add_argument("--num-videos", required=True, type=int)
    parser.add_argument("--video-path", required=True, type=str)
    parser.add_argument("--output-file", required=True, type=str)
    parser.add_argument("--max-frames", default=600, type=int)
    parser.add_argument("--process-mode", default=0, type=int)
    # Limit the number of videos that can send to one sink.
    parser.add_argument("--max-videos-per-sink", default=9, type=int)
    inputs = parser.parse_args()
    main(inputs)
    time.sleep(500)