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

class FlowService(pb2_grpc.FlowServicer):

    def __init__(self, *args, **kwargs):
        pass

    def Flow(self, request, context):
        prev_frame = np_array_decode(request.prev_frame)
        frame_image = np_array_decode(request.frame_image)
        p0 = np_array_decode(request.features)

        print(prev_frame)

        if p0 is [] or p0.shape[0] < 100:
            p0 = cv2.goodFeaturesToTrack(prev_frame,
                                         maxCorners=200,
                                         qualityLevel=0.01,
                                         minDistance=30,
                                         blockSize=3)
        print("test")
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
        return pb2.FlowResponse(**result)

def serve():
    flow_server = grpc.server(futures.ThreadPoolExecutor(max_workers=10), options=[
        ('grpc.max_send_message_length', MAX_MESSAGE_LENGTH),
        ('grpc.max_receive_message_length', MAX_MESSAGE_LENGTH)
    ])
    pb2_grpc.add_FlowServicer_to_server(FlowService(), flow_server)
    flow_server.add_insecure_port('[::]:50052')
    flow_server.start()
    flow_server.wait_for_termination()

if __name__ == '__main__':
    serve()