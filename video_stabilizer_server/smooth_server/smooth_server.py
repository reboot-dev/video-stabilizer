import grpc
from concurrent import futures
import numpy as np
import video_stabilizer_proto.video_stabilizer_pb2_grpc as pb2_grpc
import video_stabilizer_proto.video_stabilizer_pb2 as pb2
import pickle5 as pickle

MAX_MESSAGE_LENGTH = 100 * 1024 * 1024

class SmoothService(pb2_grpc.SmoothServicer):

    def __init__(self, *args, **kwargs):
        pass

    def Smooth(self, request, context):
        transform = pickle.loads(request.transforms_element)
        point = pickle.loads(request.trajectory_element)
        window = pickle.loads(request.trajectory)

        mean = np.mean(window, axis=0)
        smoothed = mean - point + transform
        result = {'final_transform': pickle.dumps(smoothed)}

        return pb2.SmoothResponse(**result)

def serve():
    smooth_server = grpc.server(futures.ThreadPoolExecutor(max_workers=10), options=[
        ('grpc.max_send_message_length', MAX_MESSAGE_LENGTH),
        ('grpc.max_receive_message_length', MAX_MESSAGE_LENGTH)
    ])
    pb2_grpc.add_SmoothServicer_to_server(SmoothService(), smooth_server)
    smooth_server.add_insecure_port('[::]:50054')
    smooth_server.start()
    smooth_server.wait_for_termination()


if __name__ == '__main__':
    serve()