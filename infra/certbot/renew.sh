#!/usr/bin/env bash
certbot renew --quiet
nginx -s reload
