#!/usr/bin/env python3

# Copyright 2021 Open Source Robotics Foundation, Inc.
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

import sys
import uuid
import time
import argparse

import rclpy
import time
from rclpy.node import Node
from rclpy.parameter import Parameter
from rmf_task_msgs.srv import SubmitTask
from rmf_task_msgs.msg import TaskType, Loop
from rmf_task_msgs.srv import GetTaskList

###############################################################################


class TaskRequester:

    def __init__(self, argv=sys.argv):
        parser = argparse.ArgumentParser()
        parser.add_argument("--use_sim_time", required=True,
                            type=str, help='Use sim time')
        parser.add_argument('-s', '--start', required=True,
                            type=str, help='Start waypoint')
        parser.add_argument('-f', '--finish', required=True,
                            type=str, help='Finish waypoint')
        parser.add_argument('-n', '--loop_num',
                            help='Number of loops to perform',
                            type=int, default=1)
        parser.add_argument('-st', '--start_time',
                            help='Start time from now in secs, default: 0',
                            type=int, default=0)
        parser.add_argument('-pt', '--priority',
                            help='Priority value for this request',
                            type=int, default=0)

        self.args = parser.parse_args(argv[1:])
        self.node = rclpy.create_node('task_requester')
        self.submit_task_srv = self.node.create_client(
            SubmitTask, '/submit_task')
        self.get_task_list_srv = self.node.create_client(
            GetTaskList, '/get_tasks')

        if self.args.use_sim_time.lower() == "false" or self.args.use_sim_time == "0":
          pass
        else:
            self.node.get_logger().info("Using Sim Time")
            param = Parameter("use_sim_time", Parameter.Type.BOOL, True)
            self.node.set_parameters([param])
            
    def _get_task_srv_is_available(self):
        if not self.get_task_list_srv.wait_for_service(timeout_sec=3.0):
          self.node.get_logger().error('Task getting service is not available')
          return False
        else:
          return True

    def generate_task_req_msg(self):
        req_msg = SubmitTask.Request()
        req_msg.description.task_type.type = TaskType.TYPE_LOOP

        loop = Loop()
        loop.num_loops = self.args.loop_num
        loop.start_name = self.args.start
        loop.finish_name = self.args.finish
        req_msg.description.loop = loop

        ros_start_time = self.node.get_clock().now().to_msg()
        ros_start_time.sec += self.args.start_time
        req_msg.description.start_time = ros_start_time

        req_msg.description.priority.value = self.args.priority
        return req_msg

    def submit_task_msg(self, req_msg):
        try:
            future = self.submit_task_srv.call_async(req_msg)
            rclpy.spin_until_future_complete(
                self.node, future, timeout_sec=1.0)
            response = future.result()
            if response is None:
                self.node.get_logger().error('/submit_task srv call failed')
                return False
            elif not response.success:
                self.node.get_logger().error(
                    'Dispatcher node failed to accept task')
                return False
            else:
                assigned_task_id = response.task_id
                self.node.get_logger().info(
                    'Request was successfully submitted '
                    f'and assigned task_id: [{assigned_task_id}]')
                
                for i in range(5): # 5 Retries to see successful fleet assignment
                    self.node.get_logger().info("Checking that Task was taken by some fleet..")
                    future = self.get_task_list_srv.call_async(GetTaskList.Request())
                    rclpy.spin_until_future_complete(self.node, future, timeout_sec=1.0)
                    response = future.result()
                    if any([x.task_id ==  assigned_task_id and x.fleet_name for x in response.active_tasks]):
                        self.node.get_logger().info("Task was successfully assigned.")
                        return True
                    else:
                        time.sleep(1)
                        
        except Exception as e:
            self.node.get_logger().error('Error! Submit Srv failed %r' % (e,))
            return False
        
    def main(self):
        rclpy.spin_once(self.node, timeout_sec=1.0)

        for i in range(5):
            self.node.get_logger().info("Attempting task submission")
            
            if not self._get_task_srv_is_available():
                self.node.get_logger().error('Task getting service is not available')
            else
                req_msg = self.generate_task_req_msg()
                self.node.get_logger().info(f"\nGenerated loop request: \n {req_msg}\n")
                success = self.submit_task_msg(req_msg)           
                if success:
                    self.node.get_logger().info("Successful submission of Loop Request")
                    return
            time.sleep(2)
        self.node.get_logger().info("Loop Task Submission unsuccessful.")
                        


###############################################################################


def main(argv=sys.argv):
    rclpy.init(args=sys.argv)
    args_without_ros = rclpy.utilities.remove_ros_args(sys.argv)

    task_requester = TaskRequester(args_without_ros)
    task_requester.main()
    rclpy.shutdown()


if __name__ == '__main__':
    main(sys.argv)

