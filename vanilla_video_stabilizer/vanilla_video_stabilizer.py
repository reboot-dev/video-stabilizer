import asyncio
import cv2
import os.path
import numpy as np
import time
import json
import threading
from collections import defaultdict
from ray.experimental.internal_kv import _internal_kv_put, \
    _internal_kv_get
import ray.cloudpickle as pickle
import psutil
import signal

import ray
import ray.cluster_utils


NUM_WORKERS_PER_VIDEO = 1


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


def flow(prev_frame, frame, p0):
    if p0 is None or p0.shape[0] < 100:
        p0 = cv2.goodFeaturesToTrack(prev_frame,
                                        maxCorners=200,
                                        qualityLevel=0.01,
                                        minDistance=30,
                                        blockSize=3)

    # Calculate optical flow (i.e. track feature points)
    p1, status, err = cv2.calcOpticalFlowPyrLK(prev_frame, frame, p0, None) 

    # Sanity check
    assert p1.shape == p0.shape 

    # Filter only valid points
    good_new = p1[status==1]
    good_old = p0[status==1]

    #Find transformation matrix
    m, _ = cv2.estimateAffinePartial2D(good_old, good_new)
        
    # Extract translation
    dx = m[0,2]
    dy = m[1,2]

    # Extract rotation angle
    da = np.arctan2(m[1,0], m[0,0])
        
    # Store transformation
    transform = [dx,dy,da]
    # Update features to track. 
    p0 = good_new.reshape(-1, 1, 2)

    return transform, p0


def cumsum(prev, next, checkpoint_key):
    sum = [i + j for i, j in zip(prev, next)]
    if checkpoint_key is not None:
        ray.experimental.internal_kv._internal_kv_put(checkpoint_key, "{} {} {}".format(*sum))
    return sum


def smooth(transform, point, *window):
    mean = np.mean(window, axis=0)
    smoothed = mean - point + transform
    return smoothed


def fixBorder(frame):
  s = frame.shape
  # Scale the image 4% without moving the center
  T = cv2.getRotationMatrix2D((s[1]/2, s[0]/2), 0, 1.04)
  frame = cv2.warpAffine(frame, T, (s[1], s[0]))
  return frame


class Viewer:
    def __init__(self, video_pathname, video_writer):
        self.video_pathname = video_pathname
        self.v = cv2.VideoCapture(video_pathname)
        self.w = video_writer

    def send(self, transform):
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

        self.w.write(frame_stabilized)

        # Write the frame to the file
        # frame_out = cv2.hconcat([frame, frame_stabilized])

        # ## If the image is too big, resize it.
        # if(frame_out.shape[1] > 1920): 
        #     frame_out = cv2.resize(frame_out, (frame_out.shape[1]//2, frame_out.shape[0]//2));
        
        # cv2.imshow("Before and After", frame_out)
        # cv2.waitKey(1)
        # out.write(frame_out)

    def ready(self):
        return


class Sink:
    def __init__(self, signal, viewer, checkpoint_interval):
        self.signal = signal
        self.num_frames_left = {}
        self.latencies = defaultdict(list)

        self.viewer = viewer
        self.last_view = None
        self.checkpoint_interval = checkpoint_interval

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

        if self.viewer is not None and video_index == 0:
            self.last_view = self.viewer.send(transform)

        if self.checkpoint_interval != 0 and frame_index % self.checkpoint_interval == 0:
            ray.experimental.internal_kv._internal_kv_put(video_index, frame_index, overwrite=True)

    def latencies(self):
        latencies = []
        for video in self.latencies.values():
            for i, l in enumerate(video):
                latencies.append((i, l))
        return latencies

    def ready(self):
        return


def process_chunk(video_index, video_pathname, sink, num_frames, fps, v07, start_timestamp, checkpoint_interval):
    decoder = Decoder(video_pathname, 0)

    # Check for a checkpoint.
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
    features = None

    frame_timestamp = start_timestamp + start_frame / fps
    diff = frame_timestamp - time.time()
    if diff > 0:
        time.sleep(diff)
    frame_timestamps.append(frame_timestamp)
    prev_frame = decoder.decode(start_frame)

    for i in range(start_frame, num_frames - 1):
        frame_timestamp = start_timestamp + (start_frame + i + 1) / fps
        diff = frame_timestamp - time.time()
        if diff > 0:
            time.sleep(diff)
        frame_timestamps.append(frame_timestamp)

        frame = decoder.decode(start_frame + i + 1)

        transform, features = flow(prev_frame, frame, features)
        # Periodically reset the features to track for better accuracy
        # (previous points may go off frame).
        if i and i % 200 == 0:
            features = None
        prev_frame = frame
        transforms.append(transform)
        if i > 0:
            if checkpoint_interval > 0 and (i + radius) % checkpoint_interval == 0:
                # Checkpoint the cumulative sum for the first frame in the
                # window centered at the frame to checkpoint.
                checkpoint_key = "{} {}".format(video_index, i + radius)
            else:
                checkpoint_key = None
            trajectory.append(cumsum(trajectory[-1], transform, checkpoint_key))
        else:
            # Add padding for the first few frames.
            for _ in range(padding):
                trajectory.append(transform)
            trajectory.append(transform)

        if len(trajectory) == 2 * radius + 1:
            midpoint = radius
            final_transform = smooth(transforms.pop(0), trajectory[midpoint], *trajectory)
            trajectory.pop(0)

            sink.send(video_index, next_to_send, final_transform, frame_timestamps.pop(0))
            next_to_send += 1

    while next_to_send < num_frames - 1:
        trajectory.append(trajectory[-1])
        midpoint = radius
        final_transform = smooth(transforms.pop(0), trajectory[midpoint], *trajectory)
        trajectory.pop(0)

        final = sink.send(video_index, next_to_send, final_transform,
                frame_timestamps.pop(0))
        next_to_send += 1
    return final


def process_videos(video_pathname, num_videos, output_filename, view,
        max_frames, num_sinks, v07, checkpoint_interval, offset_seconds):
    # An actor that will get signaled once the entire job is done.
    signal = Signal()
    signal.ready()

    video_in = cv2.VideoCapture(video_pathname)
    fps = int(video_in.get(cv2.CAP_PROP_FPS))    
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    width = int(video_in.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(video_in.get(cv2.CAP_PROP_FRAME_HEIGHT))
    video_writer = cv2.VideoWriter(output_filename, fourcc,
                     fps, (width, height))

    viewer = Viewer(video_pathname, video_writer)
    viewer.ready()

    sinks = [Sink(signal, viewer, checkpoint_interval) for i in range(num_sinks)]
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
        process_chunk(
                i, video_pathname, sinks[i % len(sinks)], num_total_frames,
                fps, v07, start_timestamp,
                checkpoint_interval)

    # Wait for all video frames to complete. It is okay to poll this actor
    # because it is not on the critical path of video processing latency.
    ready = 0
    while ready != num_videos:
        time.sleep(1)
        ready = signal.wait()

    # latencies = []
    # for sink in sinks:
    #     latencies += sink.latencies()
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
    num_sinks = args.num_videos // args.max_videos_per_sink

    # Start processing at an offset from the current time to give all processes
    # time to start up.
    offset_seconds = 5
    process_videos(args.video_path, args.num_videos, args.output,
            args.local, args.max_frames,
            num_sinks, args.v07, args.checkpoint_interval,
            offset_seconds)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run the video benchmark.")

    parser.add_argument("--num-videos", required=True, type=int)
    parser.add_argument("--video-path", required=True, type=str)
    parser.add_argument("--output", type=str)
    parser.add_argument("--v07", action="store_true")
    parser.add_argument("--failure", action="store_true")
    parser.add_argument("--owner-failure", action="store_true")
    parser.add_argument("--local", action="store_true")
    parser.add_argument("--max-frames", default=600, type=int)
    # Limit the number of videos that can send to one sink.
    parser.add_argument("--max-videos-per-sink", default=9, type=int)
    parser.add_argument("--max-sinks-per-node", default=2, type=int)
    parser.add_argument("--max-owners-per-node", default=4, type=int)
    parser.add_argument("--checkpoint-interval", default=0, type=int)
    parser.add_argument("--fail-at-seconds", default=5, type=int)
    args = parser.parse_args()
    main(args)