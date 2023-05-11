import pickle
import video_stabilizer_proto.video_stabilizer_pb2 as pb2
from video_stabilizer_clients.stabilize_client import StabilizeClient

class Stabilizer(object):
    def __init__(self,process_mode):
        self.client = StabilizeClient()
        self.process_mode = process_mode

    def stabilize(self, frame, prev_frame, features, trajectory, padding, transforms, frame_index, radius, next_to_send):
        if self.process_mode == 0:
            return self.stabilizer_grpc(frame, prev_frame, features, trajectory, padding, transforms, frame_index, radius, next_to_send)
        else:
            raise NotImplementedError
        
    def stabilize_grpc(self, frame, prev_frame, features, trajectory, padding, transforms, frame_index, radius, next_to_send):
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
    

    def stabilizeMinIO(self, frame, prev_frame, features, trajectory, padding, transforms, frame_index, radius, next_to_send):
        # convert arguments to bytes
        frame_url = ... //upload frame to minio

        # call the client and get the response
        response = self.client.stabilize(
            pb2.StabilizeRequest(
                frame_imag_url=frame_url,
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


            
