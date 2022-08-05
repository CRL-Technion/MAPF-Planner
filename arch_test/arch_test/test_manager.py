
from time import sleep
from typing import Tuple
from threading import Thread
import rclpy
from rclpy.node import Node
from tf2_ros import TransformException, TransformStamped, TransformBroadcaster
from geometry_msgs.msg import Vector3

from arch_components.planner import Planner, PlannerResponseTypes
from arch_components.manager import Manager, ManagerRequestTypes, ManagerResponseTypes
from arch_interfaces.msg import Position
from arch_interfaces.srv import AgentRequest
from mock import MagicMock

class FixedFrameBroadcaster(Node):
    def __init__(self, parent_frame_id: str, child_frame_id: str, pos: Vector3, freq: rclpy.time.Time):
        super().__init__(f'FF_{child_frame_id}_broadcaster')
        self.parent_id = parent_frame_id
        self.child_id = child_frame_id
        self.pos = pos
        self.br = TransformBroadcaster(self)
        self.timer = self.create_timer(freq, self.broadcast_timer_callback)
    
    def broadcast_timer_callback(self):
        t = TransformStamped()
        t.header.stamp = self.get_clock().now().to_msg()
        t.header.frame_id = self.parent_id
        t.child_frame_id = self.child_id
        t.transform.translation.x = self.pos.x
        t.transform.translation.y = self.pos.y
        t.transform.translation.z = self.pos.z

        self.br.sendTransform(t)

class GoalPublisher(Node):
    def __init__(self):
        super().__init__("goal_publisher")
        self.publisher = self.create_publisher(Position, "goals", 1)
    
    def publish_goal(self, goal: Position) -> None:
        self.publisher.publish(goal)

class ManagerTestClient(Node):
    def __init__(self):
        super().__init__('manager_client')
        self.cli = self.create_client(AgentRequest, 'agent_request')
    
    def create_request(self, agent_msg: str, agent_id: str):
        self.response = self.cli.call_async(AgentRequest.Request(agent_msg=agent_msg, agent_id=agent_id))

def test_transform_broadcast():
    rclpy.init()
    arena_broadcaster = FixedFrameBroadcaster("world", "arena", Vector3(x=0.0, y=0.0, z=0.0), 0.01)
    planner = Planner()

    executor = rclpy.executors.MultiThreadedExecutor()
    executor.add_node(arena_broadcaster)
    executor.add_node(planner)
    executor_thread = Thread(target=executor.spin, daemon=True)
    executor_thread.start()
    sleep(0.5)
    frame_ids = planner.get_all_frame_ids()
    assert "arena" in frame_ids and len(frame_ids) == 1

    executor.shutdown()
    arena_broadcaster.destroy_node()
    planner.destroy_node()
    rclpy.shutdown()
    executor_thread.join()

def test_agent_requests():
    rclpy.init()
    manager = Manager()

    req_mock = MagicMock()
    req_mock.agent_msg = ManagerRequestTypes.IDLE
    req_mock.agent_id = "agent_1"
    manager.agent_callback(req_mock, MagicMock())

    assert manager.unassigned_agents == ["agent_1"]

    req_mock.agent_msg = ManagerRequestTypes.AGENT_DISCONNECTED
    manager.agent_callback(req_mock, MagicMock())

    assert len(manager.unassigned_agents) == 0

    manager.destroy_node()
    rclpy.shutdown()

def test_goal_input():
    rclpy.init()
    manager = Manager()
    goal_publisher = GoalPublisher()

    executor = rclpy.executors.MultiThreadedExecutor()
    executor.add_node(manager)
    executor.add_node(goal_publisher)
    executor_thread = Thread(target=executor.spin, daemon=True)
    executor_thread.start()

    goal_1 = Position(x=50.0, y=50.0, w=1.0)
    goal_publisher.publish_goal(goal_1)
    sleep(0.5)
    assert manager.unassigned_goals == [goal_1]
    
    executor.shutdown()
    manager.destroy_node()
    goal_publisher.destroy_node()
    rclpy.shutdown()
    executor_thread.join()

def test_manager_live_request():
    rclpy.init()
    manager = Manager()
    goal_publisher = GoalPublisher()
    client = ManagerTestClient()

    executor = rclpy.executors.MultiThreadedExecutor()
    executor.add_node(manager)
    executor.add_node(goal_publisher)
    executor.add_node(client)
    executor_thread = Thread(target=executor.spin, daemon=True)
    executor_thread.start()

    goal_publisher.publish_goal(Position(x=50.0, y=50.0, w=1.0))
    client.create_request(ManagerRequestTypes.IDLE, "agent_1")

    sleep(0.5)

    assert manager.unassigned_agents == ["agent_1"]
    assert client.response.result().error_msg == ManagerResponseTypes.WAIT_PLAN
    assert manager.unassigned_goals != []

    executor.shutdown()
    manager.destroy_node()
    goal_publisher.destroy_node()
    client.destroy_node()
    rclpy.shutdown()
    executor_thread.join()

def main(args=None):
    tests = [
        # test_transform_broadcast,
        # test_agent_requests,
        test_goal_input,
        test_manager_live_request
    ]
    for test in tests:
        print(f"Running test: {test.__qualname__}", end="")
        test()
        print(" - Success")
        

if __name__ == '__main__':
    main()

