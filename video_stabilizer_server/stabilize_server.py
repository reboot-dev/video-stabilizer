import grpc
from concurrent import futures
import numpy as np
from video_stabilizer_wrappers.cumsum import CumSum
from video_stabilizer_wrappers.flow import Flow
from video_stabilizer_wrappers.smooth import Smooth
import video_stabilizer_proto.video_stabilizer_pb2_grpc as pb2_grpc
import video_stabilizer_proto.video_stabilizer_pb2 as pb2
import cv2
import pickle5 as pickle
import requests
from minio import Minio

def download_object(url):
    response = requests.get(url,timeout=10)
    if response.status_code == 200:
        return response.content
    else:
        raise Exception(f"Failed to download object from URL: {url}")

def get_process_mode(request):
    if request.HasField('frame_image'):
        return 0
    elif request.HasField('frame_image_url'):
        return 1
    else:
        return NotImplementedError

def extract_request(process_mode,request):
    if process_mode == 0:
        frame_image = pickle.loads(request.frame_image)
        prev_frame = pickle.loads(request.prev_frame)
        features = pickle.loads(request.features)
        trajectory= pickle.loads(request.trajectory)
        padding = request.padding
        transforms = pickle.loads(request.transforms)
        frame_index = request.frame_index
        radius = request.radius
        next_to_send = request.next_to_send
    elif process_mode == 1:
        frame_image = download_object(request.frame_image_url)
        prev_frame = download_object(request.prev_frame_url)
        features = download_object(request.features_url)
        trajectory = download_object(request.trajectory_url)
        padding = request.padding
        transforms = download_object(request.transforms_url)
        frame_index = request.frame_index
        radius = request.radius
        next_to_send = request.next_to_send
    else:
        raise NotImplementedError
    return (frame_image,prev_frame,features,trajectory,padding,transforms,frame_index,radius,next_to_send)

def construct_response(process_mode,client,**kwargs):
    if process_mode == 0:
        result = {'final_transform': pickle.dumps(final_transform), 'features': pickle.dumps(features), 'trajectory': pickle.dumps(trajectory), 'transforms': pickle.dumps(transforms), 'next_to_send':next_to_send}
    elif process_mode == 1:
        # put objects in Object Storage
        final_transform_bytes = pickle.dumps(final_transform)
        features_bytes = pickle.dumps(final_transform)
        trajectory_bytes = pickle.dumps(final_transform)
        transforms_bytes = pickle.dumps(final_transform)

        result = client.put_object("respect", "final_transform", final_transform_bytes, len(final_transform_bytes))
        result = client.put_object("respect", "features", features_bytes, len(features_bytes))
        result = client.put_object("respect", "trajectory", trajectory_bytes, len(trajectory_bytes))
        result = client.put_object("respect", "transforms", transforms_bytes, len(transforms_bytes))
        # get urls
        final_transform_url = client.get_presigned_url("GET","respect","final_transform",)
        features_url = client.get_presigned_url("GET","respect","features",)
        trajectory_url = client.get_presigned_url("GET","respect","trajectory",)
        transforms_url = client.get_presigned_url("GET","respect","transforms",)

        result = {'final_transform_url': final_transform_url, 'features_url': features_url, 'trajectory_url': trajectory_url, 'transforms_url': transforms_url, 'next_to_send':next_to_send}
    else:
        raise NotImplementedError
    return result


MAX_MESSAGE_LENGTH = 100 * 1024 * 1024

class StabilizeService(pb2_grpc.VideoStabilizerServicer):

    def __init__(self, *args, **kwargs):
        pass

    def Stabilize(self,request,context):
        # extract request
        process_mode = get_process_mode(request)
        (frame_image, prev_frame, features, trajectory, padding, transforms, frame_index, radius, next_to_send) = extract_request(process_mode,request)
        # logic
        flow = Flow()
        cumsum = CumSum()

        transform, features = flow.flow(prev_frame=prev_frame, frame_image=frame_image, features=features)
        # Periodically reset the features to track for better accuracy
        # (previous points may go off frame).
        if frame_index and frame_index % 200 == 0:
            features = np.empty(0)
        prev_frame = frame_image
        transforms.append(transform)
        if frame_index > 0:
            flow_response = cumsum.cumsum(trajectory_element=trajectory[-1], transform=transform)
            trajectory.append(flow_response.sum)
        else:
            # Add padding for the first few frames.
            for _ in range(padding):
                trajectory.append(transform)
            trajectory.append(transform)
        smooth = Smooth()

        # construct response
        # make Minio client
        client = Minio(
        "play.min.io",
        access_key="Q3AM3UQ867SPQQA43P2F",
        secret_key="zuf+tfteSlswRu7BJ86wekitnifILbZam1KYY3TG",
        )
        # Make 'respect' bucket if not exist.
        found = client.bucket_exists("respect")
        if not found:
            client.make_bucket("respect")

        if len(trajectory) == 2 * radius + 1:
            midpoint = radius
            smooth_response = smooth.smooth(transforms_element=transforms.pop(0), trajectory_element=trajectory[midpoint], trajectory=trajectory)
            final_transform = smooth_response.final_transform
            trajectory.pop(0)

            next_to_send += 1
            result = construct_response(process_mode,client,final_transform=final_transform,features=features,trajectory=trajectory,transforms=transforms,next_to_send=next_to_send)
        else:
            final_transform = []
            result = construct_response(process_mode,client,final_transform=final_transform,features=features,trajectory=trajectory,transforms=transforms,next_to_send=next_to_send)
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