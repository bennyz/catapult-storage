#!/bin/env python3
import eventlet
eventlet.monkey_patch(thread=False)
import logging
import functools
import os
import sys
import cinderlib as cl
import time
import threading
import signal

import grpc
import storage_pb2
import storage_pb2_grpc

from storage_pb2 import Response
from grpc_reflection.v1alpha import reflection
from concurrent import futures
from eventlet import tpool


SHUTDOWN_EVENT = threading.Event()

cl.setup(disable_logs=False)
ceph = cl.Backend(
        volume_backend_name='ceph',
        volume_driver='cinder.volume.drivers.rbd.RBDDriver',
        rbd_user='admin', rbd_pool='volumes',
        rbd_ceph_conf='/etc/ceph/ceph.conf',
        rbd_keyring_conf='/etc/ceph/ceph.client.admin.keyring',
        )

logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
log = logging.getLogger(__name__)
log.info("Finished setting cinderlib backend...")

eventlet.monkey_patch(thread=False)
class ServerProxy(tpool.Proxy):
    @staticmethod
    def _my_doit(method, *args, **kwargs):
        # cygrpc.Server methods don't acept proxied completion_queue
        unproxied_args = [arg._obj if isinstance(arg, tpool.Proxy) else arg
                          for arg in args]
        unproxied_kwargs = {k: v._obj if isinstance(v, tpool.Proxy) else v
                            for k, v in kwargs.items()}
        return method(*unproxied_args, **unproxied_kwargs)

    def __getattr__(self, attr_name):
        f = super(ServerProxy, self).__getattr__(attr_name)
        if hasattr(f, '__call__'):
            f = functools.partial(self._my_doit, f)
        return f

    def __call__(self, *args, **kwargs):
        return self._my_doit(super(ServerProxy, self).__call__,
                             *args, **kwargs)

class StorageServicer(storage_pb2_grpc.StorageServicer):
    def __init__(self, log):
        self.log = log

    def Create(self, request, context):
        self.log.info("Creating volume %s %s", request.UUID, request.size)

        try:
            ceph.create_volume(id=request.UUID, size=request.size)
        except Exception as e:
            self.log.error(e)
            return Response(status=Response.FAIL)

        return Response(status=Response.SUCCESS)

    def Remove(self, request, context):
        self.log.info("Remove")
        return storage_pb2.Response.Status.SUCCESS

    def List(self, request, context):
        self.log.info("List")
        return storage_pb2.Response.Status.SUCCESS

def shutdown_handler(signum, stack):
    signal_name = 'SIGTERM' if signum == signal.SIGTERM else 'SIGINT'
    SHUTDOWN_EVENT.set()


def stop_server(server):
    def force_stop():
        log.error('Failed to stop process, killing ourselves')
        os.kill(os.getpid(), signal.SIGKILL)

    log.info('Gracefully stopping server')
    shutdown_hadler = server.stop(60 * 10)
    shutdown_hadler.wait()

    threading.Thread(target=force_stop).start()


def serve():
    options = (
        # allow keepalive pings when there's no gRPC calls
        ('grpc.keepalive_permit_without_calls', True),
        # allow unlimited amount of keepalive pings without data
        ('grpc.http2.max_pings_without_data', 0),
        # allow grpc pings from client every 1 seconds
        ('grpc.http2.min_time_between_pings_ms', 1000),
        # allow grpc pings from client without data every 1 seconds
        ('grpc.http2.min_ping_interval_without_data_ms',  1000),
        # Support unlimited misbehaving pings
        ('grpc.http2.max_ping_strikes', 0),
    )

    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10), options=options)
    storage_pb2_grpc.add_StorageServicer_to_server(
            StorageServicer(log),
            server)

    SERVICE_NAMES = [
        storage_pb2.DESCRIPTOR.services_by_name['Storage'].full_name,
        reflection.SERVICE_NAME,
    ]

    # grpc/eventlet hack taken from https://github.com/embercsi/ember-csi/blob/5bd4dffe9107bc906d14a45cd819d9a659c19047/ember_csi/ember_csi.py#L1106-L1111
    state = server._state
    state.server = ServerProxy(state.server)
    state.completion_queue = tpool.Proxy(state.completion_queue)
    eventlet.monkey_patch(thread=False)


    reflection.enable_server_reflection(SERVICE_NAMES, server)
    server.add_insecure_port('[::]:50051')
    server.start()
    # TODO make configurable, don't hard-code
    log.info("Server started on %d...", 50051)
    #server.wait_for_termination()
    try:
        while True:
            time.sleep(60 * 60 * 24)
    except KeyboardInterrupt:
        server.stop(0)

    SHUTDOWN_EVENT.wait()
    stop_server(server)

if __name__ == '__main__':
    log.info("Starting server...")
    serve()
