import pickle
import video_stabilizer_proto.video_stabilizer_pb2 as pb2
from video_stabilizer_clients.stabilize_client import StabilizeClient
from minio import Minio

class Stabilizer(object):
    def __init__(self,process_mode):
        self.client = StabilizeClient()
        self.process_mode = process_mode

    def stabilize(self, frame_image, prev_frame, features, trajectory, padding, transforms, frame_index, radius, next_to_send):
        if self.process_mode == 0:
            return self.stabilize_grpc(frame_image, prev_frame, features, trajectory, padding, transforms, frame_index, radius, next_to_send)
        elif self.process_mode ==1:
            return self.stabilize_MinIO()
        else:
            raise NotImplementedError
        
    def stabilize_grpc(self, frame_image, prev_frame, features, trajectory, padding, transforms, frame_index, radius, next_to_send):
        # convert arguments to bytes
        frame = pickle.dumps(frame)
        prev_frame = pickle.dumps(prev_frame)
        features = pickle.dumps(features)
        trajectory = pickle.dumps(trajectory)
        transforms = pickle.dumps(transforms)

        # call the client and get the response
        response = self.client.stabilize(
            pb2.StabilizeRequest(
                frame_image=frame,
                prev_frame=prev_frame,
                features=features,
                trajectory=trajectory,
                padding=padding,
                transforms=transforms,
                frame_index=frame_index,
                radius=radius,
                next_to_send=next_to_send
            )
        )

        # convert response to python objects
        final_transform = pickle.loads(response.final_transform)
        features = pickle.loads(response.features)
        trajectory = pickle.loads(response.trajectory)
        transforms = pickle.loads(response.transforms)
        next_to_send = response.next_to_send

        return (final_transform,features,trajectory,transforms,next_to_send)
    

    def stabilizeMinIO(self, frame_image, prev_frame, features, trajectory, padding, transforms, frame_index, radius, next_to_send):
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
        # convert to bytes
        frame_image_bytes = pickle.dumps(frame_image)
        prev_frame_bytes = pickle.dumps(prev_frame)
        features_bytes = pickle.dumps(features)
        trajectory_bytes = pickle.dumps(trajectory)
        transforms_bytes = pickle.dumps(transforms)
        # put in Object Storage
        result = client.put_object("respect", "frame_image", frame_image_bytes, len(frame_image_bytes))
        result = client.put_object("respect", "prev_frame", prev_frame_bytes, len(prev_frame_bytes))
        result = client.put_object("respect", "features", features_bytes, len(features_bytes))
        result = client.put_object("respect", "trajectory", trajectory_bytes, len(trajectory_bytes))
        result = client.put_object("respect", "transforms", transforms_bytes, len(transforms_bytes))
        #get urls
        frame_image_url = client.get_presigned_url("GET","respect","frame_image",)
        prev_frame_url = client.get_presigned_url("GET","respect","prev_frame",)
        features_url = client.get_presigned_url("GET","respect","features",)
        trajectory_url = client.get_presigned_url("GET","respect","trajectory",)
        transforms_url = client.get_presigned_url("GET","respect","transforms",)

        # call the client and get the response
        response = self.client.stabilize(
            pb2.StabilizeRequest(
                frame_image_url=frame_image_url,
                prev_frame_url=prev_frame_url,
                features_url=features_url,
                trajectory_url=trajectory_url,
                padding=padding,
                transforms_url=transforms_url,
                frame_index=frame_index,
                radius=radius,
                next_to_send=next_to_send
            )
        )

        # convert response to python objects
        final_transform = pickle.loads(response.final_transform)
        features = pickle.loads(response.features)
        trajectory = pickle.loads(response.trajectory)
        transforms = pickle.loads(response.transforms)
        next_to_send = response.next_to_send

        return (final_transform,features,trajectory,transforms,next_to_send)
