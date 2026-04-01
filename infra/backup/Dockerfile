FROM alpine:3.19
RUN apk add --no-cache postgresql16-client s3cmd bash coreutils
COPY backup.sh /backup.sh
RUN chmod +x /backup.sh
COPY crontab /etc/crontabs/root
CMD ["crond", "-f", "-l", "2"]
