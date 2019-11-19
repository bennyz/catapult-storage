import logging
import functools
import sys
import cinderlib as cl
from eventlet import tpool
import grpc
import storage_pb2
from storage_pb2 import Response
import storage_pb2_grpc

from concurrent import futures

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


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))

    # grpc/eventlet hack taken from https://github.com/embercsi/ember-csi/blob/5bd4dffe9107bc906d14a45cd819d9a659c19047/ember_csi/ember_csi.py#L1106-L1111
    state = server._state
    state.server = ServerProxy(state.server)
    state.completion_queue = tpool.Proxy(state.completion_queue)
    storage_pb2_grpc.add_StorageServicer_to_server(
            StorageServicer(log),
            server)
    server.add_insecure_port('[::]:50051')
    server.start()
    server.wait_for_termination()

if __name__ == '__main__':
    log.info("Starting server...")
    serve()
