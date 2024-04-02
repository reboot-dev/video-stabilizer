import grpc
from concurrent import futures
import numpy as np
from video_stabilizer_clients.cumsum_client import CumSumClient
from video_stabilizer_clients.flow_client import FlowClient
from video_stabilizer_clients.smooth_client import SmoothClient
import video_stabilizer_proto.video_stabilizer_pb2_grpc as pb2_grpc
import video_stabilizer_proto.video_stabilizer_pb2 as pb2
import cv2
import pickle5 as pickle
import io
import json
import boto3
import os

MAX_MESSAGE_LENGTH = 100 * 1024 * 1024

def extract_stabilize_request(process_mode, request, s3_client, bucket_name):
    if process_mode == 0:
        frame_image = pickle.loads(request.stabilize_frame_data.frame_image)
        prev_frame = pickle.loads(request.stabilize_frame_data.prev_frame)
        features = pickle.loads(request.stabilize_frame_data.features)
        trajectory= pickle.loads(request.stabilize_frame_data.trajectory)
        padding = request.stabilize_frame_data.padding
        transforms = pickle.loads(request.stabilize_frame_data.transforms)
        frame_index = request.stabilize_frame_data.frame_index
        radius = request.stabilize_frame_data.radius
    elif process_mode == 1:
        stabilize_request_json_data = s3_client.get_object(Bucket=bucket_name, Key=request.stabilize_request_json_key)['Body'].read().decode("utf-8")
        stabilize_request_data = json.loads(stabilize_request_json_data)
        frame_image = pickle.loads(stabilize_request_data["frame_image"].encode('latin1'))
        prev_frame = pickle.loads(stabilize_request_data["prev_frame"].encode('latin1'))
        features = pickle.loads(stabilize_request_data["features"].encode('latin1'))
        trajectory = stabilize_request_data["trajectory"]
        padding = stabilize_request_data["padding"]
        transforms = stabilize_request_data["transforms"]
        frame_index = stabilize_request_data["frame_index"]
        radius = stabilize_request_data["radius"]
    return frame_image, prev_frame, features, trajectory, padding, transforms, frame_index, radius

def construct_stabilize_response(final_transform, features, trajectory, transforms, process_mode, s3_client, bucket_name):
    if process_mode == 0:
        final_transform_bytes = pickle.dumps(final_transform)
        features_bytes = pickle.dumps(features)
        trajectory_bytes = pickle.dumps(trajectory)
        transforms_bytes = pickle.dumps(transforms)

        stabilize_response_frame_data = pb2.StabilizeResponseFrameData(
            final_transform=final_transform_bytes,
            features=features_bytes,
            trajectory=trajectory_bytes,
            transforms=transforms_bytes
        )

        result = {'stabilize_frame_data': stabilize_response_frame_data}
    elif process_mode == 1:
        stabilize_response_data = {
            "final_transform": pickle.dumps(final_transform).decode('latin1'),
            "features": pickle.dumps(features).decode('latin1'),
            "trajectory": trajectory,
            "transforms": transforms
        }

        stabilize_response_json_data = json.dumps(stabilize_response_data)
        stabilize_response_json_data_bytes = stabilize_response_json_data.encode("utf-8")
        stabilize_response_json_data_file = io.BytesIO(stabilize_response_json_data_bytes)

        key = "stabilize_response_json"
        s3_client.put_object(Bucket=bucket_name, Key=key, Body=stabilize_response_json_data_file)
        result = {'stabilize_response_json_key': key}
    return result

def construct_flow_request(frame_image, prev_frame, features, process_mode, s3_client, bucket_name):
    if process_mode == 0:
        frame_image_bytes = pickle.dumps(frame_image)
        prev_frame_bytes = pickle.dumps(prev_frame)
        features_bytes = pickle.dumps(features)

        flow_request_frame_data = pb2.FlowRequestFrameData(
            prev_frame=prev_frame_bytes,
            frame_image=frame_image_bytes,
            features=features_bytes
        )

        flow_request = pb2.FlowRequest(
            flow_frame_data=flow_request_frame_data,
            process_mode=process_mode
        )
    elif process_mode == 1:
        flow_request_data = {
            "prev_frame": pickle.dumps(prev_frame).decode('latin1'),
            "frame_image": pickle.dumps(frame_image).decode('latin1'),
            "features": pickle.dumps(features).decode('latin1')
        }

        flow_request_json_data = json.dumps(flow_request_data)
        flow_request_json_data_bytes = flow_request_json_data.encode("utf-8")
        flow_request_json_data_file = io.BytesIO(flow_request_json_data_bytes)

        key = "flow_request_json"
        s3_client.put_object(Bucket=bucket_name, Key=key, Body=flow_request_json_data_file)
        flow_request = pb2.FlowRequest(flow_request_json_key=key, process_mode=process_mode)

    return flow_request

def extract_flow_response(flow_response, process_mode, s3_client, bucket_name):
    if process_mode == 0:
        transform = pickle.loads(flow_response.flow_frame_data.transform)
        features = pickle.loads(flow_response.flow_frame_data.features)
    elif process_mode == 1:
        flow_response_json_data = s3_client.get_object(Bucket=bucket_name, Key=flow_response.flow_response_json_key)['Body'].read().decode("utf-8")
        flow_response_data = json.loads(flow_response_json_data)
        transform = flow_response_data["transform"]
        features = pickle.loads(flow_response_data["features"].encode('latin1'))
    return transform, features

def construct_cumsum_request(trajectory, transform, process_mode, s3_client, bucket_name):
    if process_mode == 0:
        trajectory_bytes = pickle.dumps(trajectory)
        transform_bytes = pickle.dumps(transform)

        cumsum_request_frame_data = pb2.CumSumRequestFrameData(
            trajectory_element=trajectory_bytes,
            transform=transform_bytes
        )

        cumsum_request = pb2.CumSumRequest(cumsum_frame_data=cumsum_request_frame_data, process_mode=process_mode)
    elif process_mode == 1:
        cumsum_request_data = {
            "trajectory_element": trajectory,
            "transform": transform
        }

        cumsum_request_json_data = json.dumps(cumsum_request_data)
        cumsum_request_json_data_bytes = cumsum_request_json_data.encode("utf-8")
        cumsum_request_json_data_file = io.BytesIO(cumsum_request_json_data_bytes)

        key = "cumsum_request_json"
        s3_client.put_object(Bucket=bucket_name, Key=key, Body=cumsum_request_json_data_file)
        cumsum_request = pb2.CumSumRequest(cumsum_request_json_key=key, process_mode=process_mode)
    return cumsum_request

def extract_cumsum_response(cumsum_response, process_mode, s3_client, bucket_name):
    if process_mode == 0:
        sum = pickle.loads(cumsum_response.sum)
    elif process_mode == 1:
        cumsum_response_json_data = s3_client.get_object(Bucket=bucket_name, Key=cumsum_response.cumsum_response_json_key)['Body'].read().decode("utf-8")
        cumsum_response_data = json.loads(cumsum_response_json_data)
        sum = cumsum_response_data["sum"]
    return sum

def construct_smooth_request(transforms_element, trajectory_element, trajectory, process_mode, s3_client, bucket_name):
    if process_mode == 0:
        transforms_element_bytes = pickle.dumps(transforms_element)
        trajectory_element_bytes = pickle.dumps(trajectory_element)
        trajectory_bytes = pickle.dumps(trajectory)

        smooth_request_frame_data = pb2.SmoothRequestFrameData(
            transforms_element=transforms_element_bytes,
            trajectory_element=trajectory_element_bytes,
            trajectory=trajectory_bytes
        )

        smooth_request = pb2.SmoothRequest(smooth_frame_data=smooth_request_frame_data, process_mode=process_mode)
    elif process_mode == 1:
        smooth_request_data = {
            "transforms_element": transforms_element,
            "trajectory_element": trajectory_element,
            "trajectory": trajectory,
        }

        smooth_request_json_data = json.dumps(smooth_request_data)
        smooth_request_json_data_bytes = smooth_request_json_data.encode("utf-8")
        smooth_request_json_data_file = io.BytesIO(smooth_request_json_data_bytes)

        key = "smooth_request_json"
        s3_client.put_object(Bucket=bucket_name, Key=key, Body=smooth_request_json_data_file)
        smooth_request = pb2.SmoothRequest(smooth_request_json_key=key, process_mode=process_mode)
    return smooth_request

def extract_smooth_response(smooth_response, process_mode, s3_client, bucket_name):
    if process_mode == 0:
        final_transform = pickle.loads(smooth_response.final_transform)
    elif process_mode == 1:
        smooth_response_json_data = s3_client.get_object(Bucket=bucket_name, Key=smooth_response.smooth_response_json_key)['Body'].read().decode("utf-8")
        smooth_response_data = json.loads(smooth_response_json_data)
        final_transform = pickle.loads(smooth_response_data["final_transform"].encode('latin1'))
    return final_transform

class StabilizeService(pb2_grpc.VideoStabilizerServicer):

    def __init__(self, *args, **kwargs):
        pass

    def Stabilize(self, request, context):
        process_mode = request.process_mode

        if process_mode == 1:
            aws_access_key_id = os.environ["AWS_ACCESS_KEY_ID"]
            aws_secret_access_key = os.environ["AWS_SECRET_ACCESS_KEY"]
            s3_client = boto3.client('s3', aws_access_key_id=aws_access_key_id, aws_secret_access_key=aws_secret_access_key)
            bucket_name = "respect-dev-1"
        else:
            s3_client = None
            bucket_name = None

        frame_image, prev_frame, features, trajectory, padding, transforms, frame_index, radius = extract_stabilize_request(process_mode, request, s3_client, bucket_name)

        flow_client = FlowClient()
        cumsum_client = CumSumClient()

        flow_request = construct_flow_request(frame_image, prev_frame, features, process_mode, s3_client, bucket_name)
        flow_response = flow_client.flow(flow_request)
        transform, features = extract_flow_response(flow_response, process_mode, s3_client, bucket_name)

        # Periodically reset the features to track for better accuracy
        # (previous points may go off frame).
        if frame_index and frame_index % 200 == 0:
            features = np.empty(0)
        transforms.append(transform)
        if frame_index > 0:
            cumsum_request = construct_cumsum_request(trajectory[-1], transform, process_mode, s3_client, bucket_name)
            cumsum_response = cumsum_client.cumsum(cumsum_request)
            cumsum_sum = extract_cumsum_response(cumsum_response, process_mode, s3_client, bucket_name)
            trajectory.append(cumsum_sum)
        else:
            # Add padding for the first few frames.
            for _ in range(padding):
                trajectory.append(transform)
            trajectory.append(transform)
        smooth_client = SmoothClient()
        if len(trajectory) == 2 * radius + 1:
            midpoint = radius
            smooth_request = construct_smooth_request(transforms.pop(0), trajectory[midpoint], trajectory, process_mode, s3_client, bucket_name)
            smooth_response = smooth_client.smooth(smooth_request)
            final_transform = extract_smooth_response(smooth_response, process_mode, s3_client, bucket_name)
            trajectory.pop(0)

            result = construct_stabilize_response(final_transform, features, trajectory, transforms, process_mode, s3_client, bucket_name)
        else:
            result = construct_stabilize_response(None, features, trajectory, transforms, process_mode, s3_client, bucket_name)
        return pb2.StabilizeResponse(**result)

def serve():
    stabilize_server = grpc.server(futures.ThreadPoolExecutor(max_workers=10), options=[
        ('grpc.max_send_message_length', MAX_MESSAGE_LENGTH),
        ('grpc.max_receive_message_length', MAX_MESSAGE_LENGTH)
    ])
    pb2_grpc.add_VideoStabilizerServicer_to_server(StabilizeService(), stabilize_server)
    stabilize_server.add_insecure_port('[::]:50051')
    stabilize_server.start()
    stabilize_server.wait_for_termination()


if __name__ == '__main__':
    serve()