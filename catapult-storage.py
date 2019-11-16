import cinderlib as cl
import grpc
import storage_pb2
import storage_pb2_grpc
import futures

from pprint import pprint

ceph = cl.Backend(
    volume_backend_name='ceph',
    volume_driver='cinder.volume.drivers.rbd.RBDDriver',
    rbd_user='admin',
    rbd_pool='volumes',
    rbd_ceph_conf='/etc/ceph/ceph.conf',
    rbd_keyring_conf='/etc/ceph/ceph.client.admin.keyring',
)

class StorageServicer(storage_pb2_grpc.StorageServicer):
    pass

pprint(vol.dumps)
def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_worker=10))
    storage_pb2_grpc.add_StorageServicer_to_server(StorageServicer, server)
    server.add_insecure_port('[::]:50051')
    server.start()
    server.wait_for_termination()

if __name__ == '__main__':
    serve()
