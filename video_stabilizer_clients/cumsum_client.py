import grpc
import video_stabilizer_proto.video_stabilizer_pb2_grpc as pb2_grpc
import video_stabilizer_proto.video_stabilizer_pb2 as pb2

class CumSumClient(object):
    """
    Client for gRPC functionality
    """

    def __init__(self):
        # self.host = 'cs-service.cumsum-server-grpc.svc.cluster.local'
        self.host = 'localhost'
        self.server_port = 50053

        # instantiate a channel
        self.channel = grpc.insecure_channel(
            '{}:{}'.format(self.host, self.server_port))

        # bind the client and the server
        self.stub = pb2_grpc.CumSumStub(self.channel)

    def cumsum(self, cumsum_request):
        return self.stub.CumSum(cumsum_request)