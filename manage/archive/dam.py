# Библиотека для работы с форматом DAM
#
# class BinaryMesh - Обёртка вокруг корневой структуры .dam-файла
# BinaryMesh.save_obj_mtl(obj_path, mtl_path) - сохраняет данные в .obj + .mtl
#

from .dam_pb2 import binary_mesh


def _chunks(l, n):
    for i in range(0, len(l), n):
        yield l[i:i + n]


class BinaryMesh:
    def __init__(self, src=None):
        self.mesh = binary_mesh()
        if src:
            if isinstance(src, str):
                fh = open(src, 'rb')
            elif hasattr(src, 'read'):
                fh = src
            else:
                raise TypeError('BinaryMesh constructor accepts path or file-like object')
            self.mesh.ParseFromString(fh.read())

    def __getattr__(self, item):
        return getattr(self.mesh, item)

    def save_obj_mtl(self, obj_path, mtl_path):
        with open(obj_path, 'w') as fp:
            fp.write("mtllib %s\n\n" % mtl_path)
            chunks_count = []
            vertices_count = 0
            material_names = []

            for chunk in self.mesh.chunk:
                # print chunk.chunk_name+"\n"
                chunks_count.append(chunk.chunk_name)
                material_names.append(chunk.material_name)

                fp.write("usemtl %s\n" % chunk.material_name)
                fp.write("o %s\n" % chunk.chunk_name)

                vertices = list(_chunks(chunk.vertices.xyz, 3))
                uv = list(_chunks(chunk.vertices.uv, 2))
                faces = list(_chunks(chunk.faces.faces, 3))

                for v in vertices:
                    fp.write("v %.11f %.11f %.11f\n" % (v[0], v[1], v[2]))
                for vt in uv:
                    fp.write("vt %.11f %.11f\n" % (vt[0], vt[1]))

                for idx, f in enumerate(faces):
                    f0 = f[0] + 1
                    f1 = f[1] + 1
                    f2 = f[2] + 1

                    f01, f11, f21 = f0, f1, f2

                    if len(chunks_count) > 1:
                        f01, f11, f21 = vertices_count + f0, vertices_count + f1, vertices_count + f2

                    # if(len(chunks_count)>1):
                    #    f_max += len(faces)
                    #    f21 = f_max + idx + 2
                    #    f11 = f_max + idx + 3
                    #    f01 = f_max + idx + 4

                    fp.write("f %d/%d/%d %d/%d/%d %d/%d/%d\n" % (f01, f01, f0, f11, f11, f1, f21, f21, f2))

                vertices_count += len(vertices)

        with open(mtl_path, 'w') as fp:
            for material_name in material_names:
                fp.write("newmtl %s\n" % material_name)
                fp.write("map_Ka %s\n" % material_name)
                fp.write("map_Kd %s\n" % material_name)
                fp.write("Kd 1.0 1.0 1.0\n")
                fp.write("Ka 1.0 1.0 1.0\n")
                fp.write("Ks 1.0 1.0 1.0\n")
