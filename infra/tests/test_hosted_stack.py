import aws_cdk as cdk
from aws_cdk.assertions import Template

from stacks.hosted_stack import HostedStack


def _template() -> Template:
    app = cdk.App()
    stack = HostedStack(app, "TestHostedStack", env_name="test")
    return Template.from_stack(stack)


def test_stack_synthesizes_empty_for_now() -> None:
    # Skeleton: synthesizes with zero resources until Group B adds them.
    _template().resource_count_is("AWS::S3::Bucket", 0)
