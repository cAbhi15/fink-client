#!/bin/bash
# Copyright 2019 AstroLab Software
# Author: Abhishek Chauhan
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
set -e

TEST_DIR=${FINK_CLIENT_HOME}/tests

# start Kafka in docker container
docker-compose -p integration_test -f ${TEST_DIR}/docker-compose-kafka.yml up -d

# run test module
coverage run --rcfile=${FINK_CLIENT_HOME}/.coveragerc ${TEST_DIR}/test.py

# shut down kafka container
docker-compose -p integration_test -f ${TEST_DIR}/docker-compose-kafka.yml down

# measure coverage
coverage combine
coverage report
