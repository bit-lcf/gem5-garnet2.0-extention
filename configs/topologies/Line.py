# Author: David Smelt
# Adapted from: Mesh_XY.py (c) 2010 Advanced Micro Devices, Inc., 2016 Georgia Institute of Technology

import m5
from m5.params import *
from m5.objects import *

from BaseTopology import SimpleTopology
from TikzTopology import TikzTopology
from TopologyToDSENT import TopologyToDSENT


import numpy as np

class Line(SimpleTopology):
    # Creates a simple Line topology assuming an equal number of cache
    # and directory controllers.
    description='Line'

    def __init__(self, controllers):
        self.nodes = controllers
        self.tikz_out = None

    def writeTikz(self, ln):
        # Writes Tikz topology code to file

        if not self.tikz_out is None:
            self.tikz_out.write(ln)

    def makeBiLink(self, src_id, dst_id, weight, src_outport, dst_inport, IntLink):
        # Makes a bidirectional link between routers src_id and dst_id

        # src->dst link
        self.int_links.append(IntLink(link_id=self.link_count,
                                      src_node=self.routers[src_id],
                                      dst_node=self.routers[dst_id],
                                      src_outport=src_outport,
                                      dst_inport=dst_inport,
                                      latency=self.link_latency,
                                      weight=weight))

        # dst->src link
        self.int_links.append(IntLink(link_id=self.link_count + 1,
                                      src_node=self.routers[dst_id],
                                      dst_node=self.routers[src_id],
                                      src_outport=dst_inport,
                                      dst_inport=src_outport,
                                      latency=self.link_latency,
                                      weight=weight))

        thick_line = "line width=1mm" if weight == 1 else ""
        self.writeTikz("    ({0}) edge [{1}] node[] {{}} ({2})".format(src_id, thick_line, dst_id))
        self.writeTikz("    ({0}) edge [{1}] node[] {{}} ({2})".format(dst_id, thick_line, src_id))
        self.link_count += 2

    def makeTopology(self, options, network, IntLink, ExtLink, Router):
        nodes = self.nodes
        concentration_factor = options.concentration_factor
        ncpus = options.num_cpus
        nrouters = ncpus / concentration_factor
        options.mesh_rows = 1
        nrows = 1

        # First determine which nodes are cache cntrls vs. dirs vs. dma
        cache_nodes = []
        dir_nodes = []
        dma_nodes = []
        for node in nodes:
            if node.type == 'L1Cache_Controller' or node.type == 'L2Cache_Controller':
                cache_nodes.append(node)
            elif node.type == 'Directory_Controller':
                dir_nodes.append(node)
            elif node.type == 'DMA_Controller':
                dma_nodes.append(node)

        # Obviously the number of rows must be <= the number of routers
        # and evenly divisible.  Also the number of caches must be a
        # multiple of the number of routers and the number of directories
        # must be <= the number of cache nodes
        assert(nrows > 0 and nrows <= nrouters)
        ncols = int(nrouters / nrows)

        assert(ncols * nrows == nrouters)
        assert(nrouters * concentration_factor == ncpus)

        caches_per_router, remainder = divmod(len(cache_nodes), nrouters)
        assert(remainder == 0)

        ndirs = options.num_dirs
        assert(len(dir_nodes) <= len(cache_nodes))

        # Default values for link latency and router latency.
        # Can be over-ridden on a per link/router basis
        self.link_latency = options.link_latency # used by simple and garnet
        router_latency = options.router_latency # only used by garnet

        # Optionally generate Tikz topology code in 'output_directory/topo.tex' and
        # convert it to 'output_directory/topology.png'
        if options.tikz:
            self.tikz_out = TikzTopology(m5.options.outdir, nrows, ncols)

        # Create the routers on the Line
        self.routers = [Router(router_id=i, latency=router_latency) for i in range(nrouters)]
        network.routers = self.routers

        # Link counter to set unique link ids
        self.link_count = 0

        # Connect each cache node to the appropriate router
        ext_links = []
        router_id = 0
        for (i, node) in enumerate(cache_nodes):
            if i != 0 and i % caches_per_router == 0:
                router_id += 1
            ext_links.append(ExtLink(link_id=self.link_count, ext_node=node,
                                     int_node=self.routers[router_id],
                                     latency=self.link_latency))
            self.link_count += 1

       # Connect each directory node to the appropriate router
        router_id = 0
        for (i, node) in enumerate(dir_nodes):
            ext_links.append(ExtLink(link_id=self.link_count, ext_node=node,
                                     int_node=self.routers[router_id],
                                     latency=self.link_latency))
            self.link_count += 1
            router_id += nrouters / ndirs

        # Connect the DMA nodes to router 0
        for (i, node) in enumerate(dma_nodes):
            assert(node.type == 'DMA_Controller')
            ext_links.append(ExtLink(link_id=self.link_count, ext_node=node,
                                     int_node=self.routers[0],
                                     latency=self.link_latency))
            self.link_count += 1

        network.ext_links = ext_links

        # Place routers consecutively on the Line
        self.writeTikz("    \\node[main node] (0) [above left=0cm] {0};")
        for r in xrange(1, ncols):
            self.writeTikz("    \\node[main node] ({0}) [right of={{{1}}}] {{{2}}};".format(r, r - 1, r))

        self.writeTikz("\n    \\path[every node/.style={font=\\sffamily\\footnotesize},"
                       "every edge/.append style={line width=0.3mm}]")

        self.int_links = []

        # Create the ring's links
        for r in xrange(ncols - 1):
            # Destination router is east of source router
            self.makeBiLink(r, r + 1, 1, "East", "West", IntLink)

        if not self.tikz_out is None:
            self.tikz_out.close()

        network.int_links = self.int_links

        # Generate router.cfg and electrical-link.cfg for DSENT
        dsent = TopologyToDSENT(m5.options.outdir, options.link_width_bits, 
                                options.vcs_per_vnet, options.buffers_per_ctrl_vc,
                                options.buffers_per_data_vc)
