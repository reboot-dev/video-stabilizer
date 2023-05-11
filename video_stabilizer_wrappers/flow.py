import pickle
import video_stabilizer_proto.video_stabilizer_pb2 as pb2
from video_stabilizer_clients.flow_client import FlowClient

class Flow(object):
    def __init__(self,process_mode):
        self.client = FlowClient()
        self.process_mode = process_mode

    def flow(self, prev_frame, frame_image,features):
        if self.process_mode == 0:
            return self.flow_grpc(prev_frame, frame_image,features)
        else:
            raise NotImplementedError
        
    def flow_grpc(self, prev_frame, frame_image, features):
        # convert arguments to bytes
        prev_frame = pickle.dumps(prev_frame)
        frame_image = pickle.dumps(frame_image)
        features = pickle.dumps(features)


        # call the client and get the response
        response = self.client.flow(
            pb2.FlowRequest(
                prev_frame=prev_frame,
                frame_image=frame_image,
                features=features
            )
        )

        # convert response to python objects
        transform = pickle.loads(response.transform)
        features = pickle.loads(response.features)

        return (transform,features)
    




            
