import grpc
from concurrent import futures

import numpy as np
import unary.unary_pb2_grpc as pb2_grpc
import unary.unary_pb2 as pb2
import cv2

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
        self.stub = pb2_grpc.UnaryStub(self.channel)

    def flow(self, prev_frame, frame_image, features):
        flow_request = pb2.FlowRequest(prev_frame=prev_frame, frame_image=frame_image, features=features)
        return self.stub.GetFlowResponse(flow_request)

class CumSumClient(object):
    """
    Client for gRPC functionality
    """

    def __init__(self):
        self.host = 'localhost'
        self.server_port = 50053

        # instantiate a channel
        self.channel = grpc.insecure_channel(
            '{}:{}'.format(self.host, self.server_port))

        # bind the client and the server
        self.stub = pb2_grpc.UnaryStub(self.channel)

    def cumsum(self, trajectory_element, transform):
        cumsum_request = pb2.CumSumRequest(trajectory_element=trajectory_element, transform= transform)
        return self.stub.GetCumSumResponse(cumsum_request)

class StabilizeService(pb2_grpc.UnaryServicer):

    def __init__(self, *args, **kwargs):
        pass

    def GetStabilizeResponse(self, request):

        # get the frame from the incoming request
        frame_image = request.frame_image
        prev_frame = request.prev_frame
        features = request.features
        trajectory= request.trajectory
        padding = request.padding
        transforms = request.transforms
        frame_index = request.frame_index

        flow_client = FlowClient()
        cumsum_client = CumSumClient()
        result = flow_client.flow(prev_frame, frame_image, features)
        transform = result.transform
        features = result.features
        # Periodically reset the features to track for better accuracy
        # (previous points may go off frame).
        if frame_index and frame_index % 200 == 0:
            features = []
        transforms.append(transform)
        if frame_index > 0:
            result = cumsum_client.cumsum(trajectory[-1], transform)
            trajectory.append(result.sum)
        else:
            # Add padding for the first few frames.
            for _ in range(padding):
                trajectory.append(transform)
            trajectory.append(transform)

        # TODO: Should I just call smooth here every time?
        if len(trajectory) == 2 * radius + 1:
            midpoint = radius
            final_transform = smooth.options(resources={
                resource: 0.001
                }).remote(transforms.pop(0), trajectory[midpoint], *trajectory)
            trajectory.pop(0)

            sink.send.remote(next_to_send, final_transform, frame_timestamps.pop(0))
            next_to_send += 1

        result = {'stabilized_frame_image': final_transform, 'features': features, 'trajectory': trajectory, 'transforms': transforms}
        return pb2.MessageResponse(**result)

class FlowService(pb2_grpc.UnaryServicer):

    def __init__(self, *args, **kwargs):
        pass

    def GetFlowResponse(self, request):
        prev_frame = request.prev_frame
        frame_image = request.frame_image
        p0 = request.features

        if p0 is None or p0.shape[0] < 100:
            p0 = cv2.goodFeaturesToTrack(prev_frame,
                                         maxCorners=200,
                                         qualityLevel=0.01,
                                         minDistance=30,
                                         blockSize=3)

        # Calculate optical flow (i.e. track feature points)
        p1, status, err = cv2.calcOpticalFlowPyrLK(prev_frame, frame_image, p0, None) 

        # Sanity check
        assert p1.shape == p0.shape 

        # Filter only valid points
        good_new = p1[status==1]
        good_old = p0[status==1]

        #Find transformation matrix
        m, _ = cv2.estimateAffinePartial2D(good_old, good_new)
         
        # Extract translation
        dx = m[0,2]
        dy = m[1,2]

        # Extract rotation angle
        da = np.arctan2(m[1,0], m[0,0])
         
        # Store transformation
        transform = [dx,dy,da]
        # Update features to track. 
        p0 = good_new.reshape(-1, 1, 2)

        result = {'transform': transform, 'features': p0}
        return pb2.MessageResponse(**result)

class CumSumService(pb2_grpc.UnaryServicer):

    def __init__(self, *args, **kwargs):
        pass

    def GetCumSumResponse(self, request):
        prev = request.trajectory_element
        next = request.transform

        sum = [i + j for i, j in zip(prev, next)]
        result = {'sum':sum}
        return pb2.MessageResponse(**result)

def serve():
    stabilize_server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    pb2_grpc.add_UnaryServicer_to_server(StabilizeService(), stabilize_server)
    stabilize_server.add_insecure_port('[::]:50051')
    stabilize_server.start()
    #stabilize_server.wait_for_termination()

    flow_server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    pb2_grpc.add_UnaryServicer_to_server(FlowService(), flow_server)
    flow_server.add_insecure_port('[::]:50052')
    flow_server.start()
    #flow_server.wait_for_termination()

    cumsum_server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    pb2_grpc.add_UnaryServicer_to_server(CumSumService(), cumsum_server)
    cumsum_server.add_insecure_port('[::]:50053')
    cumsum_server.start()
    #cumsum_server.wait_for_termination()


if __name__ == '__main__':
    serve()