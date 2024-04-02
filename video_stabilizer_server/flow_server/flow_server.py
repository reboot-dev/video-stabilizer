import grpc
from concurrent import futures
import numpy as np
import video_stabilizer_proto.video_stabilizer_pb2_grpc as pb2_grpc
import video_stabilizer_proto.video_stabilizer_pb2 as pb2
import cv2
import pickle5 as pickle
import io
import json
import boto3
import os

MAX_MESSAGE_LENGTH = 100 * 1024 * 1024

def extract_flow_request(process_mode, request, s3_client, bucket_name):
    if process_mode == 0:
        frame_image = pickle.loads(request.flow_frame_data.frame_image)
        prev_frame = pickle.loads(request.flow_frame_data.prev_frame)
        features = pickle.loads(request.flow_frame_data.features)
    elif process_mode == 1:
        flow_request_json_data = s3_client.get_object(Bucket=bucket_name, Key=request.flow_request_json_key)['Body'].read().decode("utf-8")
        flow_request_data = json.loads(flow_request_json_data)
        frame_image = pickle.loads(flow_request_data['frame_image'].encode('latin1'))
        prev_frame = pickle.loads(flow_request_data['prev_frame'].encode('latin1'))
        features = pickle.loads(flow_request_data['features'].encode('latin1'))
    return prev_frame, frame_image, features

def construct_flow_response(transform, features, process_mode, s3_client, bucket_name):
    if process_mode == 0:
        transform_bytes = pickle.dumps(transform)
        features_bytes = pickle.dumps(features)

        flow_response_frame_data = pb2.FlowResponseFrameData(
            transform=transform_bytes,
            features=features_bytes
        )

        result = {'flow_frame_data': flow_response_frame_data}
    elif process_mode == 1:
        flow_response_data = {
            'transform': transform,
            'features': pickle.dumps(features).decode('latin1')
        }

        flow_response_json_data = json.dumps(flow_response_data)
        flow_response_json_data_bytes = flow_response_json_data.encode("utf-8")
        flow_response_json_data_file = io.BytesIO(flow_response_json_data_bytes)

        key = "flow_response_json"
        s3_client.put_object(Bucket=bucket_name, Key=key, Body=flow_response_json_data_file)
        result = {'flow_response_json_key': key}
    return result

class FlowService(pb2_grpc.FlowServicer):

    def __init__(self, *args, **kwargs):
        pass

    def Flow(self, request, context):
        process_mode = request.process_mode

        if process_mode == 1:
            aws_access_key_id = os.environ["AWS_ACCESS_KEY_ID"]
            aws_secret_access_key = os.environ["AWS_SECRET_ACCESS_KEY"]
            s3_client = boto3.client('s3', aws_access_key_id=aws_access_key_id, aws_secret_access_key=aws_secret_access_key)
            bucket_name = "respect-dev-1"
        else:
            s3_client = None
            bucket_name = None

        prev_frame, frame_image, p0 = extract_flow_request(process_mode, request, s3_client, bucket_name)

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

        result = construct_flow_response(transform, p0, process_mode, s3_client, bucket_name)
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