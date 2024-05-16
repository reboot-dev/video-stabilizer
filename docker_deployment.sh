#!/bin/bash
# delete k3d cluster
k3d cluster delete --all

./docker_image_building.sh

# start k3d cluster
k3d cluster create --config ./k3d/k3d_config.yaml

# import images to k3d cluster and deploy
k3d image import flow-server:latest -c video-stabilizer-cluster
kubectl apply -f ./k3d/flow_server_deployment.yaml

k3d image import cumsum-server:latest -c video-stabilizer-cluster
kubectl apply -f ./k3d/cumsum_server_deployment.yaml

k3d image import smooth-server:latest -c video-stabilizer-cluster
kubectl apply -f ./k3d/smooth_server_deployment.yaml

k3d image import stabilize-server:latest -c video-stabilizer-cluster
kubectl apply -f ./k3d/stabilize_server_deployment.yaml

k3d image import video-stabilizer:latest -c video-stabilizer-cluster
kubectl apply -f ./k3d/video_stabilizer_pod.yaml
sleep 300
kubectl cp video-stabilizer-grpc/video-stabilizer-pod:app/stabilized_video/stabilized_video.mp4 /workspaces/video-stabilizer/stabilized_video/stabilized_video.mp4