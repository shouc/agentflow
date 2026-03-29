"""EC2 runner: launch instance, SSH execute, terminate."""

from __future__ import annotations

import asyncio
import base64

from agentflow.prepared import ExecutionPaths, PreparedExecution
from agentflow.runners.base import (
    CancelCallback,
    LaunchPlan,
    RawExecutionResult,
    Runner,
    StreamCallback,
)
from agentflow.runners.ssh import SSHRunner
from agentflow.specs import NodeSpec


class EC2Runner(Runner):
    """Launch a fresh EC2 instance, execute via SSH, then terminate."""

    def _launch_instance(self, node: NodeSpec, prepared: PreparedExecution) -> str:
        import boto3

        target = node.target
        ec2 = boto3.client("ec2", region_name=target.region)

        params: dict = {
            "ImageId": target.ami,
            "InstanceType": target.instance_type,
            "MinCount": 1,
            "MaxCount": 1,
            "TagSpecifications": [
                {
                    "ResourceType": "instance",
                    "Tags": [{"Key": "Name", "Value": f"agentflow-{node.id}"}],
                }
            ],
        }
        if target.key_name:
            params["KeyName"] = target.key_name
        if target.security_group_ids:
            params["SecurityGroupIds"] = target.security_group_ids
        if target.subnet_id:
            params["SubnetId"] = target.subnet_id

        user_data_parts: list[str] = []
        if target.install_agents:
            from agentflow.cloud.installer import agent_install_script

            user_data_parts.append(agent_install_script(target.install_agents))
        if target.user_data:
            user_data_parts.append(target.user_data)
        if user_data_parts:
            params["UserData"] = base64.b64encode(
                "\n".join(user_data_parts).encode()
            ).decode()

        if target.spot:
            params["InstanceMarketOptions"] = {"MarketType": "spot"}

        response = ec2.run_instances(**params)
        return response["Instances"][0]["InstanceId"]

    def _wait_for_ssh(self, region: str, instance_id: str) -> str:
        import boto3

        ec2 = boto3.client("ec2", region_name=region)
        waiter = ec2.get_waiter("instance_running")
        waiter.wait(InstanceIds=[instance_id], WaiterConfig={"Delay": 5, "MaxAttempts": 60})
        waiter = ec2.get_waiter("instance_status_ok")
        waiter.wait(InstanceIds=[instance_id], WaiterConfig={"Delay": 10, "MaxAttempts": 30})

        response = ec2.describe_instances(InstanceIds=[instance_id])
        instance = response["Reservations"][0]["Instances"][0]
        return instance.get("PublicIpAddress") or instance.get("PrivateIpAddress")

    def _terminate_instance(self, region: str, instance_id: str) -> None:
        import boto3

        boto3.client("ec2", region_name=region).terminate_instances(InstanceIds=[instance_id])

    def plan_execution(
        self,
        node: NodeSpec,
        prepared: PreparedExecution,
        paths: ExecutionPaths,
    ) -> LaunchPlan:
        target = node.target
        return LaunchPlan(
            kind="ec2",
            command=prepared.command,
            env=prepared.env,
            cwd=str(paths.target_workdir),
            payload={
                "ami": target.ami,
                "instance_type": target.instance_type,
                "region": target.region,
                "spot": getattr(target, "spot", False),
            },
        )

    async def execute(
        self,
        node: NodeSpec,
        prepared: PreparedExecution,
        paths: ExecutionPaths,
        on_output: StreamCallback,
        should_cancel: CancelCallback,
    ) -> RawExecutionResult:
        target = node.target
        instance_id: str | None = None
        try:
            if should_cancel():
                return RawExecutionResult(
                    exit_code=130, stdout_lines=[], stderr_lines=["Cancelled"],
                    timed_out=False, cancelled=True,
                )

            await on_output("stderr", f"Launching EC2 {target.instance_type} ({target.ami})...")
            instance_id = await asyncio.to_thread(self._launch_instance, node, prepared)
            await on_output("stderr", f"Instance {instance_id} launched, waiting for SSH...")

            if should_cancel():
                return RawExecutionResult(
                    exit_code=130, stdout_lines=[], stderr_lines=["Cancelled during launch"],
                    timed_out=False, cancelled=True,
                )

            ip = await asyncio.to_thread(self._wait_for_ssh, target.region, instance_id)
            await on_output("stderr", f"Instance ready at {ip}, executing...")

            from types import SimpleNamespace

            ssh_target = SimpleNamespace(
                kind="ssh", host=ip, port=22,
                username=target.username,
                identity_file=target.key_name,
                remote_workdir=None,
            )
            ssh_node = SimpleNamespace(
                id=node.id, target=ssh_target,
                timeout_seconds=node.timeout_seconds,
            )
            return await SSHRunner().execute(ssh_node, prepared, paths, on_output, should_cancel)
        except Exception as exc:
            return RawExecutionResult(
                exit_code=1, stdout_lines=[],
                stderr_lines=[f"EC2 execution failed: {exc}"],
                timed_out=False, cancelled=False,
            )
        finally:
            if instance_id:
                await on_output("stderr", f"Terminating {instance_id}...")
                try:
                    await asyncio.to_thread(self._terminate_instance, target.region, instance_id)
                    await on_output("stderr", f"Instance {instance_id} terminated.")
                except Exception as exc:
                    await on_output("stderr", f"Warning: failed to terminate {instance_id}: {exc}")
