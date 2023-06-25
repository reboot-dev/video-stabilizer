import grpc
from concurrent import futures
import numpy as np
import video_stabilizer_proto.video_stabilizer_pb2_grpc as pb2_grpc
import video_stabilizer_proto.video_stabilizer_pb2 as pb2
import cv2
import pickle5 as pickle
import requests
from minio import Minio

MAX_MESSAGE_LENGTH = 100 * 1024 * 1024

def download_object(url):
    response = requests.get(url,timeout=10)
    if response.status_code == 200:
        return response.content
    else:
        raise Exception(f"Failed to download object from URL: {url}")
def get_process_mode(request):
    if request.HasField('prev_frame'):
        return 0
    elif request.HasField('prev_frame_url'):
        return 1
    else:
        return NotImplementedError
def extract_request(process_mode,request):
    if process_mode == 0:
        prev_frame = pickle.loads(request.prev_frame)
        frame_image = pickle.loads(request.frame_image)
        p0 = pickle.loads(request.features)
    elif process_mode == 1:
        prev_frame = download_object(request.prev_frame_url)
        frame_image = download_object(request.frame_image_url)
        p0 = download_object(request.features_url)
    else:
        return NotImplementedError
    return prev_frame,frame_image,p0
def construct_response(process_mode,client,**kwargs):
    if process_mode == 0:
        result = {'transform': pickle.dumps(transform), 'features': pickle.dumps(p0)}
    elif process_mode == 1:
        transform_bytes = pickle.dumps(transform)
        features_bytes = pickle.dumps(p0)
        result = client.put_object("respect", "transform", transform_bytes, len(transform_bytes))
        result = client.put_object("respect", "features", features_bytes, len(features_bytes))
        transform_url = client.get_presigned_url("GET","respect","transform",)
        features_url = client.get_presigned_url("GET","respect","features",)
        result = {'transform_url': transform_url, 'features_url': features_url}
    else:
        return NotImplementedError
    return result

class FlowService(pb2_grpc.FlowServicer):

    def __init__(self, *args, **kwargs):
        pass
    
    # wip
    def Flow(self, request, context):
        # extract request
        process_mode = get_process_mode(request)
        prev_frame,frame_image,p0 = extract_request(process_mode,request)
        #logic
        if p0 is [] or p0.shape[0] < 100:
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

        client = Minio("play.min.io",
        access_key="Q3AM3UQ867SPQQA43P2F",
        secret_key="zuf+tfteSlswRu7BJ86wekitnifILbZam1KYY3TG",)
        # Make 'respect' bucket if not exist.
        found = client.bucket_exists("respect")
        if not found:
            client.make_bucket("respect")        

        result = construct_response(process_mode,client,transform=transform,p0=p0)
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