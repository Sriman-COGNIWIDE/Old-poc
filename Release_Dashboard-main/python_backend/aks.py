from flask import Flask, jsonify
from kubernetes import client
import urllib3
import re
from flask_cors import CORS
import os
from functools import wraps
from collections import defaultdict, namedtuple
import time
from datetime import datetime, date

app = Flask(__name__, static_folder='public')
CORS(app, resources={r"/api/*": {"origins": "*", "methods": ["GET", "OPTIONS", "POST"], "allow_headers": ["Content-Type"]}})

CACHE_DURATIONS = {
    "poc": 120,
    "dev": 120,
    "staging": 120,
    "prod": 120
}

CLUSTERS = {
    "poc": {
        "minikube": {
            "host": "https://3.145.118.147:8443",
            "token": os.environ.get("MINIKUBE_TOKEN")
        },
        "aks-pe-poc": {
            "host": "https://aks-pe-poc-dns-t2aw702d.hcp.centralindia.azmk8s.io:443",
            "token": os.environ.get("AKS_TOKEN")
        }
    },
    "dev": {
        "minikube": {
            "host": "https://3.145.118.147:8443",
            "token": os.environ.get("MINIKUBE_TOKEN")
        }
    }
}

VERSION_PATTERN = re.compile(r':([^:@]+)(?:@sha256:.+)?$')

k8s_clients = {env: {} for env in CLUSTERS.keys()}

CacheInfo = namedtuple('CacheInfo', ['hits', 'misses', 'maxsize', 'currsize'])

class EnvironmentCache:
    def __init__(self, maxsize=256):
        self.maxsize = maxsize
        self.cache = defaultdict(dict)
        self.cache_info_data = defaultdict(lambda: {"hits": 0, "misses": 0})
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

    def cache_info(self):
        total_hits = sum(info["hits"] for info in self.cache_info_data.values())
        total_misses = sum(info["misses"] for info in self.cache_info_data.values())
        total_size = sum(len(cache) for cache in self.cache.values())
        return CacheInfo(total_hits, total_misses, self.maxsize, total_size)

    def env_cache_info(self, env):
        info = self.cache_info_data[env]
        size = len(self.cache.get(env, {}))
        return CacheInfo(info["hits"], info["misses"], self.maxsize, size)

    def cache_clear(self, env=None):
        if env is None:
            self.cache.clear()
            self.cache_info_data.clear()
            self.last_access_time.clear()
        else:
            if env in self.cache:
                del self.cache[env]
                del self.cache_info_data[env]
                del self.last_access_time[env]

    def __call__(self, func):
        @wraps(func)
        def wrapper(cluster_name, env, timestamp):
            cache_key = (cluster_name, timestamp)
            current_time = time.time()
            cache_timestamp = self.get_cache_timestamp(env, current_time)
            
            if current_time > (cache_timestamp + CACHE_DURATIONS[env]):
                self.cache[env].clear()  
                self.last_access_time[env] = current_time  
                cache_timestamp = current_time
                cache_key = (cluster_name, cache_timestamp)
            
            if cache_key in self.cache[env]:
                self.cache_info_data[env]["hits"] += 1
                return self.cache[env][cache_key]
            
            self.cache_info_data[env]["misses"] += 1
            result = func(cluster_name, env, cache_timestamp)
            
            self.cache[env][cache_key] = result
            
            if len(self.cache[env]) > self.maxsize:
                oldest_key = min(self.cache[env].keys(), key=lambda k: k[1])
                self.cache[env].pop(oldest_key)
            
            return result
        return wrapper

cluster_cache = EnvironmentCache(maxsize=256)

def get_formatted_time():
    return datetime.now().strftime("%I:%M %p")

def get_formatted_date():
    return datetime.now().strftime("%d-%m-%Y")

def initialize_k8s_clients(env):
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    for cluster_name, cluster_info in CLUSTERS[env].items():
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

def get_cache_timestamp(env):
    return cluster_cache.get_cache_timestamp(env)

@cluster_cache
def get_cluster_info_cached(cluster_name, env, timestamp):
    return get_cluster_info(cluster_name, env, CACHE_DURATIONS[env], timestamp)

def get_cluster_info(cluster_name, env, cache_duration, cache_timestamp):
    try:
        if cluster_name not in k8s_clients[env]:
            return {
                "status": "error",
                "error": {
                    "type": "ClusterNotFound",
                    "message": f"Cluster '{cluster_name}' not found in {env} environment"
                }
            }
        
        clients = k8s_clients[env][cluster_name]
        cluster_info = []
        current_time = get_formatted_time()
        current_date = get_formatted_date()
        namespaces = clients["core_v1"].list_namespace()
        
        for ns in namespaces.items:
            namespace_name = ns.metadata.name
            deployments = clients["apps_v1"].list_namespaced_deployment(namespace_name)
            
            for deployment in deployments.items:
                deployment_info = {
                    "deployment-name": deployment.metadata.name,
                    "namespace": namespace_name,
                    "cluster": cluster_name,
                    "main-containers": process_container_images(deployment.spec.template.spec.containers),
                    "init-containers": process_container_images(deployment.spec.template.spec.init_containers) if deployment.spec.template.spec.init_containers else [],
                }
                cluster_info.append(deployment_info)
        
        return {"status": "success", "data": cluster_info, "time": current_time, "date": current_date}

    except Exception as e:
        return {
            "status": "error",
            "error": {
                "type": "GeneralException",
                "message": str(e)
            }
        }

@app.route('/api/<env>', methods=['GET'])
def get_deployments_by_env(env):
    try:
        env = env.lower()
        if env not in CLUSTERS:
            return jsonify({
                "status": "error",
                "error": {
                    "type": "InvalidEnvironment",
                    "message": f"Environment '{env}' not supported"
                },
                "time": get_formatted_time(),
                "date": get_formatted_date()
            }), 404

        if not k8s_clients[env]:
            initialize_k8s_clients(env)

        timestamp = get_cache_timestamp(env)
        all_deployments = []
        response_time = None
        response_date = None
        
        for cluster_name in CLUSTERS[env].keys():
            result = get_cluster_info_cached(cluster_name, env, timestamp)
            if result.get("status") == "success":
                all_deployments.extend(result["data"])
                if not response_time:
                    response_time = result.get("time")
                    response_date = result.get("date")
        
        return jsonify({
            "status": "success",
            "data": all_deployments,
            "date_time": f"{response_date or get_formatted_date()} {response_time or get_formatted_time()}"
        })
            
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": {
                "type": "GeneralException",
                "message": str(e)
            },
            "time": get_formatted_time(),
            "date": get_formatted_date()
        }), 500

@app.route('/api/cache/refresh/<env>', methods=['POST'])
def refresh_env_cache(env):
    try:
        env = env.lower()
        if env not in CLUSTERS:
            return jsonify({
                "status": "error",
                "error": {
                    "type": "InvalidEnvironment",
                    "message": f"Environment '{env}' not supported"
                },
                "data": [],
                "time": get_formatted_time(),
                "date": get_formatted_date()
            }), 404

        cluster_cache.cache_clear(env)
        
        if k8s_clients[env]:
            k8s_clients[env].clear()
        initialize_k8s_clients(env)

        timestamp = get_cache_timestamp(env)
        all_deployments = []
        response_time = None
        response_date = None

        for cluster_name in CLUSTERS[env].keys():
            result = get_cluster_info_cached(cluster_name, env, timestamp)
            if result.get("status") == "success":
                all_deployments.extend(result["data"])
                if not response_time:
                    response_time = result.get("time")
                    response_date = result.get("date")

        return jsonify({
            "status": "success",
            "message": f"Cache cleared and refreshed for {env} environment",
            "data": all_deployments,
            "time": response_time or get_formatted_time(),
            "date": response_date or get_formatted_date()
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "error": {
                "type": "GeneralException",
                "message": str(e)
            },
            "data": [],
            "time": get_formatted_time(),
            "date": get_formatted_date()
        }), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "healthy",
        "time": get_formatted_time(),
        "date": get_formatted_date()
    })

@app.route('/api/clusters', methods=['GET'])
def list_clusters():
    all_clusters = {
        env: list(clients.keys())
        for env, clients in k8s_clients.items()
    }
    return jsonify({
        "status": "success",
        "data": all_clusters,
        "time": get_formatted_time(),
        "date": get_formatted_date()
    })

@app.route('/api/cache/clear', methods=['POST'])
def clear_cache():
    try:
        cluster_cache.cache_clear()
        
        for env in k8s_clients:
            k8s_clients[env].clear()
        
        return jsonify({
            "status": "success",
            "message": "Cache cleared successfully",
            "time": get_formatted_time(),
            "date": get_formatted_date()
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": {
                "type": "GeneralException",
                "message": str(e)
            },
            "time": get_formatted_time(),
            "date": get_formatted_date()
        }), 500

@app.route('/api/cache/status', methods=['GET'])
def get_cache_status():
    try:
        current_time = time.time()
        
        cache_status = {}
        for env in CLUSTERS.keys():
            env_cache_info = cluster_cache.env_cache_info(env)
            last_access = cluster_cache.last_access_time.get(env)
            cache_status[env] = {
                "hits": env_cache_info.hits,
                "misses": env_cache_info.misses,
                "currsize": env_cache_info.currsize,
                "duration": CACHE_DURATIONS[env],
                "last_access": datetime.fromtimestamp(last_access).strftime("%I:%M %p") if last_access else None
            }

        total_cache_info = cluster_cache.cache_info()
        
        return jsonify({
            "status": "success",
            "cache_info": {
                "total": {
                    "hits": total_cache_info.hits,
                    "misses": total_cache_info.misses,
                    "maxsize": total_cache_info.maxsize,
                    "currsize": total_cache_info.currsize,
                },
                "environments": cache_status
            },
            "current_time": datetime.fromtimestamp(current_time).strftime("%I:%M %p"),
            "time": get_formatted_time(),
            "date": get_formatted_date()
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": {
                "type": "GeneralException",
                "message": str(e)
            },
            "time": get_formatted_time(),
            "date": get_formatted_date()
        }), 500

@app.route('/api/cache/timestamp', methods=['GET'])
def get_current_timestamp():
    try:
        current_time = time.time()
        cache_timestamps = {}
        
        for env in CLUSTERS.keys():
            last_access = cluster_cache.last_access_time.get(env)
            cache_timestamps[env] = {
                "timestamp": cluster_cache.get_cache_timestamp(env),
                "duration": CACHE_DURATIONS[env],
                "last_access": last_access
            }
            
        return jsonify({
            "status": "success",
            "time": get_formatted_time(),
            "current_timestamp": current_time,
            "cache_timestamps": cache_timestamps
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": {
                "type": "GeneralException",
                "message": str(e)
            },
            "time": get_formatted_time()
        }), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)