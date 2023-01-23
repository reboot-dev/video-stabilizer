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

    def get_stabilized_frame_image(self, frame_image, prev_frame, padding, frame_index):
        # Client function to call the rpc for StabilizeRequest

        # frame_image_request = pb2.StabilizeRequest(frame_image=frame_image, prev_frame=prev_frame, features=features, trajectory=trajectory, padding=padding, transforms=transforms, frame_index=frame_index)
        frame_image_request = pb2.StabilizeRequest(frame_image=frame_image, prev_frame=prev_frame, padding=padding, frame_index=frame_index)
        return self.stub.Stabilize(frame_image_request)