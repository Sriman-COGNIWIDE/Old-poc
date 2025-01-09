import json
import urllib3
from kubernetes import client
import re
from collections import defaultdict
import time
from datetime import datetime
import boto3
from botocore.exceptions import ClientError

VERSION_PATTERN = re.compile(r':([^:@]+)(?:@sha256:.+)?$')

CACHE_DURATIONS = {
    "poc": 120,
    "dev": 120,
    "staging": 120,
    "prod": 120
}

class EnvironmentCache:
    def __init__(self, maxsize=256):
        self.maxsize = maxsize
        self.cache = defaultdict(dict)
        self.last_access_time = defaultdict(float)

    def get_cache_timestamp(self, env, current_time=None):
        if current_time is None:
            current_time = time.time()
        
        if not self.last_access_time[env]:
            self.last_access_time[env] = current_time
            return current_time
        
        time_elapsed = current_time - self.last_access_time[env]
        duration = CACHE_DURATIONS[env]
        intervals = int(time_elapsed / duration)
        
        return self.last_access_time[env] + (intervals * duration)

    def cache_clear(self, env=None):
        if env is None:
            self.cache.clear()
            self.last_access_time.clear()
        else:
            if env in self.cache:
                del self.cache[env]
                del self.last_access_time[env]

    def __call__(self, func):
        def wrapper(cluster_name, env, timestamp, *args, **kwargs):
            cache_key = (cluster_name, timestamp)
            current_time = time.time()
            cache_timestamp = self.get_cache_timestamp(env, current_time)
            
            if current_time > (cache_timestamp + CACHE_DURATIONS[env]):
                self.cache[env].clear()
                self.last_access_time[env] = current_time
                cache_timestamp = current_time
                cache_key = (cluster_name, cache_timestamp)
            
            if cache_key in self.cache[env]:
                return self.cache[env][cache_key]
            
            result = func(cluster_name, env, cache_timestamp, *args, **kwargs)
            
            self.cache[env][cache_key] = result
            
            if len(self.cache[env]) > self.maxsize:
                oldest_key = min(self.cache[env].keys(), key=lambda k: k[1])
                self.cache[env].pop(oldest_key)
            
            return result
        return wrapper

cluster_cache = EnvironmentCache(maxsize=256)

def get_secret(secret_name):
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name='ap-south-1'
    )

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
    except ClientError as e:
        raise e
    else:
        if 'SecretString' in get_secret_value_response:
            secret_dict = json.loads(get_secret_value_response['SecretString'])
            for host, token in secret_dict.items():
                return {"host": host, "token": token}
    return None

def init_clusters():
    try:
        minikube_creds = get_secret('cluster_creds')
        aks_creds = get_secret('aks_creds')

        if not minikube_creds or not aks_creds:
            raise Exception("Failed to retrieve cluster credentials from Secrets Manager")

        cluster_config = {
            "poc": {
                "minikube": minikube_creds,
                "aks-pe-poc": aks_creds
            },
            "dev": {
                "minikube": minikube_creds
            }
        }
        return cluster_config
    except Exception as e:
        print(f"Error initializing clusters: {str(e)}")
        raise

k8s_clients = {env: {} for env in ["poc", "dev"]}

def get_formatted_datetime():
    return datetime.now().strftime("%d-%m-%Y %I:%M %p")

def initialize_k8s_clients(env, clusters):
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    for cluster_name, cluster_info in clusters[env].items():
        configuration = client.Configuration()
        configuration.host = cluster_info["host"]
        configuration.verify_ssl = False
        configuration.api_key = {"authorization": f"Bearer {cluster_info['token']}"}
        
        api_client = client.ApiClient(configuration)
        k8s_clients[env][cluster_name] = {
            "apps_v1": client.AppsV1Api(api_client),
            "core_v1": client.CoreV1Api(api_client)
        }

def extract_version_from_image(image_string):
    match = VERSION_PATTERN.search(image_string)
    if not match:
        return "None"
    return match.group(1)

def process_container_images(containers):
    if not containers:
        return []
    return [{
        "image": container.image,
        "version": extract_version_from_image(container.image)
    } for container in containers]

@cluster_cache
def get_cluster_deployments(cluster_name, env, timestamp, clients):
    try:
        if cluster_name not in clients[env]:
            return {'deployments': [], 'timestamp': get_formatted_datetime()}
        
        cluster_clients = clients[env][cluster_name]
        deployments_list = []
        
        namespaces = cluster_clients["core_v1"].list_namespace()
        
        for ns in namespaces.items:
            namespace_name = ns.metadata.name
            deployments = cluster_clients["apps_v1"].list_namespaced_deployment(namespace_name)
            
            for deployment in deployments.items:
                deployment_info = {
                    "cluster": cluster_name,
                    "deployment-name": deployment.metadata.name,
                    "namespace": namespace_name,
                    "main-containers": process_container_images(deployment.spec.template.spec.containers),
                    "init-containers": process_container_images(deployment.spec.template.spec.init_containers) if deployment.spec.template.spec.init_containers else []
                }
                deployments_list.append(deployment_info)
        
        return {
            'deployments': deployments_list,
            'timestamp': get_formatted_datetime()
        }
    except Exception as e:
        print(f"Error getting deployments for cluster {cluster_name}: {str(e)}")
        return {'deployments': [], 'timestamp': get_formatted_datetime()}

def get_deployments_for_env(env, clusters, refresh_cache=False):
    if refresh_cache:
        cluster_cache.cache_clear(env)
        if k8s_clients[env]:
            k8s_clients[env].clear()
        initialize_k8s_clients(env, clusters)
    
    if not k8s_clients[env]:
        initialize_k8s_clients(env, clusters)
        
    timestamp = cluster_cache.get_cache_timestamp(env)
    all_deployments = []
    cached_timestamp = None
    
    for cluster_name in clusters[env].keys():
        result = get_cluster_deployments(cluster_name, env, timestamp, k8s_clients)
        all_deployments.extend(result['deployments'])
        if cached_timestamp is None:
            cached_timestamp = result['timestamp']
    
    return all_deployments, cached_timestamp

def clear_all_caches():
    cluster_cache.cache_clear()
    for env in k8s_clients:
        k8s_clients[env].clear()

def lambda_handler(event, context):
    try:
        path = event.get('path', '')
        print(f"Received path: {path}") 
        if path.endswith('/'):
            path = path[:-1]
            
        if path == '/api/health':
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'status': 'healthy',
                    'date_time': get_formatted_datetime()
                })
            }
            
        path = path.lstrip('/')
        path_parts = path.split('/')
        
        if not path_parts or path_parts[0] != 'api':
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'status': 'error',
                    'error': {
                        'type': 'InvalidPath',
                        'message': 'Path must start with /api/'
                    }
                })
            }

        clusters = init_clusters()
        
        if path == 'api/clear/cache' and http_method == 'POST':
            clear_all_caches()
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'status': 'success',
                    'message': 'All caches cleared successfully',
                    'date_time': get_formatted_datetime()
                })
            }
        
        if len(path_parts) == 2:
            env = path_parts[1].lower()
            
            if env not in clusters:
                return {
                    'statusCode': 404,
                    'body': json.dumps({
                        'status': 'error',
                        'error': {
                            'type': 'InvalidEnvironment',
                            'message': f"Environment '{env}' not supported"
                        }
                    })
                }
                
            all_deployments, cached_time = get_deployments_for_env(env, clusters)
            
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'status': 'success',
                    'data': all_deployments,
                    'date_time': cached_time
                })
            }
            
        if len(path_parts) == 4 and path_parts[1] == 'cache' and path_parts[2] == 'refresh' and http_method == 'POST':
            env = path_parts[3].lower()
            
            if env not in clusters:
                return {
                    'statusCode': 404,
                    'body': json.dumps({
                        'status': 'error',
                        'error': {
                            'type': 'InvalidEnvironment',
                            'message': f"Environment '{env}' not supported"
                        }
                    })
                }
                
            all_deployments, cached_time = get_deployments_for_env(env, clusters, refresh_cache=True)
            
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'status': 'success',
                    'data': all_deployments,
                    'date_time': cached_time
                })
            }
            
        return {
            'statusCode': 404,
            'body': json.dumps({
                'status': 'error',
                'error': {
                    'type': 'RouteNotFound',
                    'message': 'The requested route does not exist'
                }
            })
        }
        
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({
                'status': 'error',
                'error': {
                    'type': 'GeneralException',
                    'message': str(e)
                }
            })
        }