import grpc
import video_stabilizer_proto.video_stabilizer_pb2_grpc as pb2_grpc
import video_stabilizer_proto.video_stabilizer_pb2 as pb2

class StabilizeClient(object):
    # Client for gRPC functionality

    def __init__(self):
        self.host = 'localhost'
        self.server_port = 50051

        # instantiate a channel
        self.channel = grpc.insecure_channel(
            '{}:{}'.format(self.host, self.server_port))

        # bind the client and the server
        self.stub = pb2_grpc.VideoStabilizerStub(self.channel)

    def stabilize(self, frame_image_request):
        # Client function to call the rpc for StabilizeRequest

        return self.stub.Stabilize(frame_image_request)