import aws_cdk as core
import aws_cdk.assertions as assertions

from jfc.jfc_stack import JfcStack

# example tests. To run these tests, uncomment this file along with the example
# resource in jfc/jfc_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = JfcStack(app, "jfc")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
