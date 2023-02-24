import grpc
from concurrent import futures
import numpy as np
from video_stabilizer_clients.cumsum_client import CumSumClient
from video_stabilizer_clients.flow_client import FlowClient
from video_stabilizer_clients.smooth_client import SmoothClient
import video_stabilizer_proto.video_stabilizer_pb2_grpc as pb2_grpc
import video_stabilizer_proto.video_stabilizer_pb2 as pb2
import cv2
import pickle5 as pickle

MAX_MESSAGE_LENGTH = 100 * 1024 * 1024

class StabilizeService(pb2_grpc.VideoStabilizerServicer):

    def __init__(self, *args, **kwargs):
        pass

    def Stabilize(self, request, context):
        # get the frame from the incoming request
        frame_image = pickle.loads(request.frame_image)
        prev_frame = pickle.loads(request.prev_frame)
        features = pickle.loads(request.features)
        trajectory= pickle.loads(request.trajectory)
        padding = request.padding
        transforms = pickle.loads(request.transforms)
        frame_index = request.frame_index
        radius = request.radius
        next_to_send = request.next_to_send

        flow_client = FlowClient()
        cumsum_client = CumSumClient()

        flow_response = flow_client.flow(pb2.FlowRequest(prev_frame=pickle.dumps(prev_frame), frame_image=pickle.dumps(frame_image), features=pickle.dumps(features)))
        transform = pickle.loads(flow_response.transform)
        features = pickle.loads(flow_response.features)
        # Periodically reset the features to track for better accuracy
        # (previous points may go off frame).
        if frame_index and frame_index % 200 == 0:
            features = np.empty(0)
        prev_frame = frame_image
        transforms.append(transform)
        if frame_index > 0:
            flow_response = cumsum_client.cumsum(pb2.CumSumRequest(trajectory_element=pickle.dumps(trajectory[-1]), transform=pickle.dumps(transform)))
            trajectory.append(pickle.loads(flow_response.sum))
        else:
            # Add padding for the first few frames.
            for _ in range(padding):
                trajectory.append(transform)
            trajectory.append(transform)
        smooth_client = SmoothClient()
        if len(trajectory) == 2 * radius + 1:
            midpoint = radius
            smooth_response = smooth_client.smooth(pb2.SmoothRequest(transforms_element=pickle.dumps(transforms.pop(0)), trajectory_element=pickle.dumps(trajectory[midpoint]), trajectory=pickle.dumps(trajectory)))
            final_transform = pickle.loads(smooth_response.final_transform)
            trajectory.pop(0)

            next_to_send += 1
            result = {'final_transform': pickle.dumps(final_transform), 'features': pickle.dumps(features), 'trajectory': pickle.dumps(trajectory), 'transforms': pickle.dumps(transforms), 'next_to_send':next_to_send}
        else:
            result = {'final_transform': pickle.dumps([]), 'features': pickle.dumps(features), 'trajectory': pickle.dumps(trajectory), 'transforms': pickle.dumps(transforms), 'next_to_send':next_to_send}
        return pb2.StabilizeResponse(**result)

def serve():
    stabilize_server = grpc.server(futures.ThreadPoolExecutor(max_workers=10), options=[
        ('grpc.max_send_message_length', MAX_MESSAGE_LENGTH),
        ('grpc.max_receive_message_length', MAX_MESSAGE_LENGTH)
    ])
    pb2_grpc.add_VideoStabilizerServicer_to_server(StabilizeService(), stabilize_server)
    stabilize_server.add_insecure_port('[::]:50051')
    stabilize_server.start()
    stabilize_server.wait_for_termination()


if __name__ == '__main__':
    serve()