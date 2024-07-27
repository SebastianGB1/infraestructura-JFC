from aws_cdk import (
    CfnOutput,
    Stack,
    aws_cloudfront,
    aws_s3,
    RemovalPolicy,
    aws_cloudfront_origins,
    aws_wafv2 as aws_waf,
    aws_ec2,
    aws_autoscaling,
    aws_elasticloadbalancingv2,
    aws_rds,
    aws_cloudwatch
)
from constructs import Construct


class JfcStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.app_config = self.node.try_get_context("app_config")
        self.construct_id = construct_id

        # Front resources
        self.create_s3_bucket()
        self.create_waf_and_rules()
        self.create_cloudfront_distribution(True)

        # Back resources
        self.create_vpc()
        self.create_security_group()
        self.create_autoscaling_group()
        self.create_load_balancer()

        # Datos resources
        self.create_rds_db()

        # Alarmas
        self.add_cloudwatch_alarms()

        # Outputs
        self.add_cloudformation_outputs()

    def create_s3_bucket(self):
        '''
        Method to create S3 bucket to store the static content
        '''
        self.s3_bucket = aws_s3.Bucket(
            self,
            f'{self.app_config["app_name"]}-bucket',
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

    def create_cloudfront_distribution(self, add_waf: bool):
        '''
        Method to create CloudFront distribution to serve the static content
        '''
        self.cloudfront_distribution = aws_cloudfront.Distribution(
            self,
            f'{self.app_config["app_name"]}-CFDistribution',
            default_behavior=aws_cloudfront.BehaviorOptions(
                origin=aws_cloudfront_origins.S3Origin(self.s3_bucket)),
            web_acl_id=self.waf.attr_arn if add_waf else None,
        )

    def create_vpc(self):
        '''
        Method to create VPC
        '''
        self.vpc = aws_ec2.Vpc(
            self,
            f'{self.app_config["app_name"]}-VPC',
            cidr="10.0.0.0/16",
            max_azs=2,
            nat_gateways=1,
            subnet_configuration=[
                aws_ec2.SubnetConfiguration(
                    name="public",
                    subnet_type=aws_ec2.SubnetType.PUBLIC,
                    cidr_mask=24
                ),
                aws_ec2.SubnetConfiguration(
                    name="private",
                    subnet_type=aws_ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24
                )
            ]
        )

    def create_security_group(self):
        '''
        Method to create Security Group
        '''
        self.security_group = aws_ec2.SecurityGroup(
            self,
            f'{self.app_config["app_name"]}-SecurityGroup',
            vpc=self.vpc,
            allow_all_outbound=True
        )
        # Los puertos se configuran segun las necesidades de la aplicacion
        self.security_group.add_ingress_rule(aws_ec2.Peer.any_ipv4(), aws_ec2.Port.tcp(
            22), "Allow SSH access") if self.app_config["ec2"]["allow_ssh"] else None
        self.security_group.add_ingress_rule(aws_ec2.Peer.any_ipv4(), aws_ec2.Port.tcp(
            80), "Allow HTTP access") if self.app_config["ec2"]["allow_http"] else None
        self.security_group.add_ingress_rule(aws_ec2.Peer.any_ipv4(), aws_ec2.Port.tcp(
            443), "Allow HTTPS access") if self.app_config["ec2"]["allow_https"] else None

    def create_autoscaling_group(self):
        '''
        Method to create Auto Scaling Group
        '''
        self.autoscaling_group = aws_autoscaling.AutoScalingGroup(
            self,
            f'{self.app_config["app_name"]}-AutoScalingGroup',
            vpc=self.vpc,
            instance_type=aws_ec2.InstanceType(
                self.app_config["ec2"]["instance_type"]),
            machine_image=aws_ec2.MachineImage.generic_linux(
                ami_map={"us-east-1": "ami-04a81a99f5ec58529"}),
            security_group=self.security_group,
            min_capacity=self.app_config["ec2"]["min_capacity"],
            max_capacity=self.app_config["ec2"]["max_capacity"]
        )
        self.autoscaling_group.scale_on_cpu_utilization(
            "CPUUtilization",
            target_utilization_percent=50
        )

    def create_load_balancer(self):
        '''
        Method to create Load Balancer
        '''
        self.load_balancer = aws_elasticloadbalancingv2.ApplicationLoadBalancer(
            self,
            f'{self.app_config["app_name"]}-LoadBalancer',
            vpc=self.vpc,
            internet_facing=True,
            security_group=self.security_group
        )
        listener = self.load_balancer.add_listener(
            f'{self.app_config["app_name"]}-Listener',
            port=80,
            open=False
        )
        listener.add_targets(
            f'{self.app_config["app_name"]}-Targets',
            port=80,
            targets=[self.autoscaling_group]
        )

    def create_rds_db(self):
        '''
        Method to create RDS database
        '''

        self.db = aws_rds.DatabaseInstance(
            self,
            f'{self.app_config["app_name"]}-DataBase',
            engine=aws_rds.DatabaseInstanceEngine.POSTGRES,
            instance_type=aws_ec2.InstanceType.of(
                aws_ec2.InstanceClass.BURSTABLE3, aws_ec2.InstanceSize.SMALL),
            vpc=self.vpc,
            security_groups=[self.security_group],
            removal_policy=RemovalPolicy.DESTROY,
            cloudwatch_logs_exports=["postgresql", "upgrade"],
            delete_automated_backups=False,
            multi_az=True,
        )

    def add_cloudwatch_alarms(self):
        aws_cloudwatch.Alarm(
            self,
            "WAF-alert",
            metric=aws_cloudwatch.Metric(
                namespace="AWS/CloudFront",
                metric_name="4xxErrorRate",
                dimensions_map={
                    "DistributionId": self.cloudfront_distribution.distribution_id
                }
            ),
            threshold=1,
            evaluation_periods=1,
            comparison_operator=aws_cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
            alarm_description="Alarma para el porcentaje de errores 4xx en CloudFront."
        )

        aws_cloudwatch.Alarm(
            self,
            id="HighCPU-DB",
            metric=self.db.metric_cpu_utilization(),
            threshold=90,
            evaluation_periods=1,
            alarm_description="Alarma para el porcetaje de CPU utilizado en base de datos"
        )

        aws_cloudwatch.Alarm(
            self,
            id="HighConnections-DB",
            metric=self.db.metric("DatabaseConnections"),
            threshold=1000,
            evaluation_periods=1,
            alarm_description="Alarma para el numero de conexiones a la base de datos"
        )

    def add_cloudformation_outputs(self):
        '''
        Method to add CloudFormation outputs
        '''
        CfnOutput(
            self,
            "BucketName",
            value=self.s3_bucket.bucket_name,
            description="Nombre del bucket S3"
        )
        CfnOutput(
            self,
            "DistributionDomain",
            value=self.cloudfront_distribution.domain_name,
            description="Dominio del distribuido CloudFront"
        )