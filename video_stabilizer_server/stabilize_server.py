import grpc
from concurrent import futures

import numpy as np
from video_stabilizer_clients.cumsum_client import CumSumClient
from video_stabilizer_clients.flow_client import FlowClient
import video_stabilizer_proto.video_stabilizer_pb2_grpc as pb2_grpc
import video_stabilizer_proto.video_stabilizer_pb2 as pb2
import cv2

class StabilizeService(pb2_grpc.VideoStabilizerServicer):

    def __init__(self, *args, **kwargs):
        pass

    def Stabilize(self, request):

        # get the frame from the incoming request
        frame_image = request.frame_image
        prev_frame = request.prev_frame
        features = request.features
        trajectory= request.trajectory
        padding = request.padding
        transforms = request.transforms
        frame_index = request.frame_index

        flow_client = FlowClient()
        cumsum_client = CumSumClient()
        result = flow_client.flow(prev_frame, frame_image, features)
        transform = result.transform
        features = result.features
        # Periodically reset the features to track for better accuracy
        # (previous points may go off frame).
        if frame_index and frame_index % 200 == 0:
            features = []
        transforms.append(transform)
        if frame_index > 0:
            result = cumsum_client.cumsum(trajectory[-1], transform)
            trajectory.append(result.sum)
        else:
            # Add padding for the first few frames.
            for _ in range(padding):
                trajectory.append(transform)
            trajectory.append(transform)

        # TODO: Should I just call smooth here every time?
        # if len(trajectory) == 2 * radius + 1:
        #     midpoint = radius
        #     final_transform = smooth.options(resources={
        #         resource: 0.001
        #         }).remote(transforms.pop(0), trajectory[midpoint], *trajectory)
        #     trajectory.pop(0)

        #     sink.send.remote(next_to_send, final_transform, frame_timestamps.pop(0))
        #     next_to_send += 1

        result = {'stabilized_frame_image': final_transform, 'features': features, 'trajectory': trajectory, 'transforms': transforms}
        return pb2.StabilizeResponse(**result)

def serve():
    stabilize_server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    pb2_grpc.add_VideoStabilizerServicer_to_server(StabilizeService(), stabilize_server)
    stabilize_server.add_insecure_port('[::]:50051')
    stabilize_server.start()
    stabilize_server.wait_for_termination()


if __name__ == '__main__':
    serve()