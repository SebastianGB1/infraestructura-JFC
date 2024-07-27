#!/usr/bin/env python3
import os

import aws_cdk as cdk

from jfc.jfc_stack import JfcStack


app = cdk.App()
JfcStack(app, "JfcStack",

         env=cdk.Environment(account='654654139729', region='us-east-1'),

         )

app.synth()
