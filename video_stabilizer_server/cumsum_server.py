import grpc
from concurrent import futures
import numpy as np
import video_stabilizer_proto.video_stabilizer_pb2_grpc as pb2_grpc
import video_stabilizer_proto.video_stabilizer_pb2 as pb2
import pickle5 as pickle

MAX_MESSAGE_LENGTH = 100 * 1024 * 1024

class CumSumService(pb2_grpc.CumSumServicer):

    def __init__(self, *args, **kwargs):
        pass

    def CumSum(self, request, context):
        prev = pickle.loads(request.trajectory_element)
        next = pickle.loads(request.transform)

        sum = [i + j for i, j in zip(prev, next)]
        result = {'sum':pickle.dumps(sum)}
        return pb2.CumSumResponse(**result)

def serve():
    cumsum_server = grpc.server(futures.ThreadPoolExecutor(max_workers=10), options=[
        ('grpc.max_send_message_length', MAX_MESSAGE_LENGTH),
        ('grpc.max_receive_message_length', MAX_MESSAGE_LENGTH)
    ])
    pb2_grpc.add_CumSumServicer_to_server(CumSumService(), cumsum_server)
    cumsum_server.add_insecure_port('[::]:50053')
    cumsum_server.start()
    cumsum_server.wait_for_termination()


if __name__ == '__main__':
    serve()