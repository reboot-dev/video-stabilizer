import grpc
import video_stabilizer_proto.video_stabilizer_pb2_grpc as pb2_grpc
import video_stabilizer_proto.video_stabilizer_pb2 as pb2

class SmoothClient(object):
    """
    Client for gRPC functionality
    """

    def __init__(self):
        # self.host = 'ss-service.smooth-server-grpc.svc.cluster.local'
        self.host = 'localhost'
        self.server_port = 50054

        # instantiate a channel
        self.channel = grpc.insecure_channel(
            '{}:{}'.format(self.host, self.server_port))

        # bind the client and the server
        self.stub = pb2_grpc.SmoothStub(self.channel)

    def smooth(self, smooth_request):
        
        return self.stub.Smooth(smooth_request)