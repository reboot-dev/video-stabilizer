import grpc
from concurrent import futures

import numpy as np
from video_stabilizer_clients.cumsum_client import CumSumClient
from video_stabilizer_clients.flow_client import FlowClient
import video_stabilizer_proto.video_stabilizer_pb2_grpc as pb2_grpc
import video_stabilizer_proto.video_stabilizer_pb2 as pb2
import cv2

class CumSumService(pb2_grpc.CumSumServicer):

    def __init__(self, *args, **kwargs):
        pass

    def CumSum(self, request):
        prev = request.trajectory_element
        next = request.transform

        sum = [i + j for i, j in zip(prev, next)]
        result = {'sum':sum}
        return pb2.CumSumResponse(**result)

def serve():
    cumsum_server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    pb2_grpc.add_CumSumServicer_to_server(CumSumService(), cumsum_server)
    cumsum_server.add_insecure_port('[::]:50053')
    cumsum_server.start()
    cumsum_server.wait_for_termination()


if __name__ == '__main__':
    serve()