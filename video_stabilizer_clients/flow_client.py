import grpc
import video_stabilizer_proto.video_stabilizer_pb2_grpc as pb2_grpc
import video_stabilizer_proto.video_stabilizer_pb2 as pb2

class FlowClient(object):
    """
    Client for gRPC functionality
    """

    def __init__(self):
        self.host = 'localhost'
        self.server_port = 50052

        # instantiate a channel
        self.channel = grpc.insecure_channel(
            '{}:{}'.format(self.host, self.server_port))

        # bind the client and the server
        self.stub = pb2_grpc.FlowStub(self.channel)

    def flow(self, flow_request):
        # flow_request = pb2.FlowRequest(prev_frame=prev_frame, frame_image=frame_image, features=features)
        return self.stub.Flow(flow_request)