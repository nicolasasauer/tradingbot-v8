FROM freqtradeorg/freqtrade:stable

# Bundle user_data in the image so the bot works when no volume is mounted.
COPY user_data/ /freqtrade/user_data/

# Keep a separate copy of the defaults so the entrypoint can initialise an
# empty bind-mount volume on first run (fresh deployment with only docker-compose.yml).
COPY user_data/ /freqtrade/user_data_defaults/

# Custom entrypoint: populates an empty user_data volume before starting freqtrade.
COPY --chmod=755 docker-entrypoint.sh /docker-entrypoint.sh

ENTRYPOINT ["/docker-entrypoint.sh"]
