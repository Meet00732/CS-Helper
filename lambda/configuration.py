import boto3
import os

class Configuration:
    def __init__(self):
        self.ssm = boto3.client('ssm', region_name='us-east-1')
        self.cache = {}

    
    def get_parameter(self, name, with_decryption=False):
        """
        Fetch a parameter from SSM Parameter Store.
        Caches the result for subsequent calls.
        """
        if name in self.cache:
            return self.cache[name]
        
        response = self.ssm.get_parameter(
            Name=name,
            WithDecryption=with_decryption
        )
        value = response['Parameter']['Value']
        self.cache[name] = value

        return value
    
configuration = Configuration()
