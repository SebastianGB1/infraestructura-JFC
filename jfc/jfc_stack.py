from aws_cdk import (
    # Duration,
    Stack,
    aws_cloudfront,
    aws_s3,
    RemovalPolicy,
    aws_cloudfront_origins,
    aws_wafv2 as aws_waf,
    aws_ec2
)
from constructs import Construct

class JfcStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.app_config = self.node.try_get_context("app_config")
        self.construct_id = construct_id

        self.create_s3_bucket()
        self.create_waf_and_rules()
        self.create_cloudfront_distribution(True)

    def create_s3_bucket(self):
        '''
        Method to create S3 bucket to store the static content
        '''
        self.s3_bucket= aws_s3.Bucket(
            self,
            f'{self.app_config["app_name"]}-bucket',
            bucket_name=f'{self.app_config["app_name"].lower()}-bucket2',
            removal_policy=RemovalPolicy.DESTROY,
        )

    def create_waf_and_rules(self):
        '''
        Method to create WAF Web ACL
        '''
        self.waf = aws_waf.CfnWebACL(
            self,
            f'{self.app_config["app_name"]}-WAF',
            default_action=aws_waf.CfnWebACL.DefaultActionProperty(
                allow={}
            ),
            scope="CLOUDFRONT",
            visibility_config=aws_waf.CfnWebACL.VisibilityConfigProperty(
                cloud_watch_metrics_enabled=True,
                metric_name="waf-metrics",
                sampled_requests_enabled=True
            ),
            rules=[
                aws_waf.CfnWebACL.RuleProperty(
                    name="WAF-IPRateLimitingRule",
                    priority=1,
                    # override_action=aws_waf.CfnWebACL.OverrideActionProperty(
                    #     none={}
                    # ),
                    statement=aws_waf.CfnWebACL.StatementProperty(
                        rate_based_statement=aws_waf.CfnWebACL.RateBasedStatementProperty(
                            limit=1000,
                            aggregate_key_type="IP"
                        )
                    ),
                    action=aws_waf.CfnWebACL.RuleActionProperty(
                        block={}
                    ),
                    visibility_config=aws_waf.CfnWebACL.VisibilityConfigProperty(
                        cloud_watch_metrics_enabled=True,
                        metric_name="IPRateLimitingRule",
                        sampled_requests_enabled=True
                    )
                )
            ]
        )


    def create_cloudfront_distribution(self, add_waf:bool):
        '''
        Method to create CloudFront distribution to serve the static content
        '''
        self.cloudfront_distribution = aws_cloudfront.Distribution(
            self,
            f'{self.app_config["app_name"]}-CFDistribution',
            default_behavior=aws_cloudfront.BehaviorOptions(origin=aws_cloudfront_origins.S3Origin(self.s3_bucket)),
            web_acl_id=self.waf.attr_arn if add_waf else None,
        )

    def create_vpc(self):
        '''
        Method to create VPC
        '''
        self.vpc = aws_ec2.Vpc.from_lookup(
            self,
            f'{self.app_config["app_name"]}-VPC',
            is_default=True
        )

    def create_ec2_instance(self):
        '''
        Method to create EC2 instance
        '''
        self.ec2 = aws_ec2.Instance(
            self,
            f'{self.app_config["app_name"]}-EC2Instance',
            instance_type=aws_ec2.InstanceType("t2.micro"),
            machine_image=aws_ec2.AmazonLinuxImage(),
            vpc=self.vpc,
        )


