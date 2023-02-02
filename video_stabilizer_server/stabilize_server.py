import grpc
from concurrent import futures
import numpy as np
from video_stabilizer_clients.cumsum_client import CumSumClient
from video_stabilizer_clients.flow_client import FlowClient
import video_stabilizer_proto.video_stabilizer_pb2_grpc as pb2_grpc
import video_stabilizer_proto.video_stabilizer_pb2 as pb2
import cv2

MAX_MESSAGE_LENGTH = 100 * 1024 * 1024

def list_encode(lst):
    return bytes(lst)

def list_decode(b):
    return list(b)

def np_array_encode(lst):
    return np.ndarray.tobytes(lst)

def np_array_decode(b):
    return np.frombuffer(b)

class StabilizeService(pb2_grpc.VideoStabilizerServicer):

    def __init__(self, *args, **kwargs):
        pass

    def Stabilize(self, request, context):
        # get the frame from the incoming request
        frame_image = request.frame_image
        prev_frame = request.prev_frame
        print(np_array_decode(prev_frame))
        features = np_array_decode(request.features)
        trajectory= list_decode(request.trajectory)
        padding = request.padding
        transforms = list_decode(request.transforms)
        frame_index = request.frame_index

        flow_client = FlowClient()
        cumsum_client = CumSumClient()
        result = flow_client.flow(pb2.FlowRequest(prev_frame=prev_frame, frame_image=frame_image, features=np_array_encode(features)))
        transform = list_decode(result.transform)
        features = np_array_decode(result.features)
        # Periodically reset the features to track for better accuracy
        # (previous points may go off frame).
        if frame_index and frame_index % 200 == 0:
            features = []
        transforms.append(transform)
        if frame_index > 0:
            result = cumsum_client.cumsum(pb2.CumSumRequest(trajectory_element=list_encode(trajectory[-1]), transform=list_encode(transform)))
            trajectory.append(list_decode(result.sum))
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

        # result = {'stabilized_frame_image': final_transform, 'features': features, 'trajectory': trajectory, 'transforms': transforms}
        result = {'stabilized_frame_image': final_transform, 'features': list_encode(features), 'trajectory': list_encode(features), 'transforms': list_encode(transforms)}
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