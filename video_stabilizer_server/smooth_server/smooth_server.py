import grpc
from concurrent import futures
import numpy as np
import video_stabilizer_proto.video_stabilizer_pb2_grpc as pb2_grpc
import video_stabilizer_proto.video_stabilizer_pb2 as pb2
import pickle5 as pickle
import io
import json
import boto3
import os

MAX_MESSAGE_LENGTH = 100 * 1024 * 1024

def extract_smooth_request(process_mode, request, s3_client, bucket_name):
    if process_mode == 0:
        transform = pickle.loads(request.smooth_frame_data.transforms_element)
        point = pickle.loads(request.smooth_frame_data.trajectory_element)
        window = pickle.loads(request.smooth_frame_data.trajectory)
    elif process_mode == 1:
        smooth_request_json_data = s3_client.get_object(Bucket=bucket_name, Key=request.smooth_request_json_key)['Body'].read().decode("utf-8")
        smooth_request_data = json.loads(smooth_request_json_data)
        transform = smooth_request_data['transforms_element']
        point = smooth_request_data['trajectory_element']
        window = smooth_request_data['trajectory']
    return transform, point, window

def construct_smooth_response(smoothed, process_mode, s3_client, bucket_name):
    if process_mode == 0:
        final_transform_bytes = pickle.dumps(smoothed)
        result = {'final_transform': final_transform_bytes}
    elif process_mode == 1:
        smooth_response_data = {
            'final_transform': pickle.dumps(smoothed).decode('latin1')
        }

        smooth_response_json_data = json.dumps(smooth_response_data)
        smooth_response_json_data_bytes = smooth_response_json_data.encode("utf-8")
        smooth_response_json_data_file = io.BytesIO(smooth_response_json_data_bytes)

        key = "smooth_response_json"
        s3_client.put_object(Bucket=bucket_name, Key=key, Body=smooth_response_json_data_file)
        result = {'smooth_response_json_key': key}
    return result

class SmoothService(pb2_grpc.SmoothServicer):

    def __init__(self, *args, **kwargs):
        pass

    def Smooth(self, request, context):
        process_mode = request.process_mode

        if process_mode == 1:
            aws_access_key_id = os.environ["AWS_ACCESS_KEY_ID"]
            aws_secret_access_key = os.environ["AWS_SECRET_ACCESS_KEY"]
            s3_client = boto3.client('s3', aws_access_key_id=aws_access_key_id, aws_secret_access_key=aws_secret_access_key)
            bucket_name = "respect-dev-1"
        else:
            s3_client = None
            bucket_name = None

        transform, point, window = extract_smooth_request(process_mode, request, s3_client, bucket_name)

        mean = np.mean(window, axis=0)
        smoothed = mean - point + transform
        result = construct_smooth_response(smoothed, process_mode, s3_client, bucket_name)

        return pb2.SmoothResponse(**result)

def serve():
    smooth_server = grpc.server(futures.ThreadPoolExecutor(max_workers=10), options=[
        ('grpc.max_send_message_length', MAX_MESSAGE_LENGTH),
        ('grpc.max_receive_message_length', MAX_MESSAGE_LENGTH)
    ])
    pb2_grpc.add_SmoothServicer_to_server(SmoothService(), smooth_server)
    smooth_server.add_insecure_port('[::]:50054')
    smooth_server.start()
    smooth_server.wait_for_termination()


if __name__ == '__main__':
    serve()