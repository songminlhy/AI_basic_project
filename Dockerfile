FROM alpine:3.19
LABEL maintainer="harness-ci-test"
RUN echo "Harness ECR push validation image" > /version.txt
CMD ["cat", "/version.txt"]
