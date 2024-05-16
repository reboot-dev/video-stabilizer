FROM base:latest

COPY video_stabilizer.zip app/
COPY video_example/husky.mp4 app/video_example/
RUN mkdir -p /app/stabilized_video/
CMD ["python", "/app/video_stabilizer.zip", "--num-videos", "1", "--video-path", "/app/video_example/husky.mp4", "--output-file", "/app/stabilized_video/stabilized_video.mp4", "--process-mode", "0", "--max-videos-per-sink", "1"]