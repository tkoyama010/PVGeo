__all__ = [
    'ManySlicesAlongPoints',
    'ManySlicesAlongAxis',
    'SlideSliceAlongPoints',
    'SliceThroughTime'
]

__displayname__ = 'Slicing'

import numpy as np
import vtk
from vtk.numpy_interface import dataset_adapter as dsa

import pyvista as pv

from .. import _helpers, interface
from ..base import FilterBase


class _SliceBase(FilterBase):
    """A helper class for making slicing fileters

    Note:
        * Make sure the input data source is slice-able.
        * The SciPy module is required for this filter.
    """
    __displayname__ = 'Base Slicing Filter'
    __category__ = 'filter'

    def __init__(self, n_slices=5,
                 nInputPorts=1, inputType='vtkDataSet',
                 nOutputPorts=1, outputType='vtkUnstructuredGrid'):
        FilterBase.__init__(self,
                            nInputPorts=nInputPorts, inputType=inputType,
                            nOutputPorts=nOutputPorts, outputType=outputType)
        # Parameters
        self.__n_slices = n_slices


    @staticmethod
    def _generate_plane(origin, normal):
        """Internal helper to build a ``vtkPlane`` for the cutter
        """
        # Get the slicing Plane:
        plane = vtk.vtkPlane() # Construct the plane object
        # Set the origin... needs to be inside of the grid
        plane.SetOrigin(origin[0], origin[1], origin[2])
        # set normal of that plane so we look at XZ section
        plane.SetNormal(normal)
        return plane

    @staticmethod
    def _slice(pdi, pdo, plane):
        """Slice an input on a plane and produce the output
        """
        # create slice
        cutter = vtk.vtkCutter() # Construct the cutter object
        cutter.SetInputData(pdi) # Use the grid as the data we desire to cut
        cutter.SetCutFunction(plane) # the the cutter to use the plane we made
        cutter.Update() # Perfrom the Cut
        slc = cutter.GetOutput() # grab the output
        pdo.ShallowCopy(slc)

        return pdo

    def get_number_of_slices(self):
        """Retun the number of slices generated by this algorithm"""
        return self.__n_slices

    def set_number_of_slices(self, num):
        """Set the number of slices generated by this algorithm"""
        if self.__n_slices != num:
            self.__n_slices = num
            self.Modified()


###############################################################################


class ManySlicesAlongPoints(_SliceBase):
    """Takes a series of points and a data source to be sliced. The points are
    used to construct a path through the data source and a slice is added at
    intervals of that path along the vector of that path at that point. This
    constructs many slices through the input dataset as a merged
    ``vtkMultiBlockDataSet``.

    Note:
        * Make sure the input data source is slice-able.
        * The SciPy module is required for this filter.
    """
    __displayname__ = 'Many Slices Along Points'
    __category__ = 'filter'

    def __init__(self, n_slices=5, nearest_nbr=True, outputType='vtkMultiBlockDataSet'):
        _SliceBase.__init__(self, n_slices=n_slices,
                            nInputPorts=2, inputType='vtkDataSet',
                            nOutputPorts=1, outputType=outputType)
        self.__useNearestNbr = nearest_nbr

    # CRITICAL for multiple input ports
    def FillInputPortInformation(self, port, info):
        """This simply makes sure the user selects the correct inputs
        """
        typ = 'vtkDataSet'
        if port == 0:
            typ = 'vtkPolyData' # Make sure points are poly data
        info.Set(self.INPUT_REQUIRED_DATA_TYPE(), typ)
        return 1

    def _get_planes(self, pts):
        """Internal helper to generate planes for the slices"""
        try:
            # sklearn's KDTree is faster: use it if available
            from sklearn.neighbors import KDTree as Tree
        except ImportError:
            from scipy.spatial import cKDTree as Tree
        if self.get_number_of_slices() == 0:
            return []
        # Get the Points over the NumPy interface
        wpdi = dsa.WrapDataObject(pts) # NumPy wrapped points
        points = np.array(wpdi.Points) # New NumPy array of points so we dont destroy input
        numPoints = pts.GetNumberOfPoints()
        if self.__useNearestNbr:
            tree = Tree(points)
            ptsi = tree.query([points[0]], k=numPoints)[1].ravel()
        else:
            ptsi = [i for i in range(numPoints)]

        # Iterate of points in order (skips last point):
        planes = []
        for i in range(0, numPoints - 1, numPoints//self.get_number_of_slices()):
            # get normal
            pts1 = points[ptsi[i]]
            pts2 = points[ptsi[i+1]]
            x1, y1, z1 = pts1[0], pts1[1], pts1[2]
            x2, y2, z2 = pts2[0], pts2[1], pts2[2]
            normal = [x2-x1,y2-y1,z2-z1]
            # create plane
            plane = self._generate_plane([x1,y1,z1], normal)
            planes.append(plane)

        return planes

    def _get_slice(self, pts, data, planes, output):
        """Internal helper to perfrom the filter
        """
        numPoints = pts.GetNumberOfPoints()
        # Set number of blocks based on user choice in the selction
        output.SetNumberOfBlocks(self.get_number_of_slices())
        blk = 0
        for i, plane in enumerate(planes):
            temp = vtk.vtkPolyData()
            self._slice(data, temp, plane)
            output.SetBlock(blk, temp)
            output.GetMetaData(blk).Set(vtk.vtkCompositeDataSet.NAME(), 'Slice%.2d' % blk)
            blk += 1
        return output


    def RequestData(self, request, inInfo, outInfo):
        """Used by pipeline to generate output"""
        # Get input/output of Proxy
        pts = self.GetInputData(inInfo, 0, 0) # Port 0: points
        data = self.GetInputData(inInfo, 1, 0) # Port 1: sliceable data
        output = vtk.vtkMultiBlockDataSet.GetData(outInfo, 0)
        # Perfrom task
        planes = self._get_planes(pts)
        self._get_slice(pts, data, planes, output)
        return 1



    #### Getters / Setters ####


    def set_use_nearest_nbr(self, flag):
        """Set a flag on whether to use SciPy's nearest neighbor approximation
        when generating the slicing path
        """
        if self.__useNearestNbr != flag:
            self.__useNearestNbr = flag
            self.Modified()

    def apply(self, points, data):
        """Run the algorithm along some points for the given input data"""
        self.SetInputDataObject(0, points)
        self.SetInputDataObject(1, data)
        self.Update()
        return pv.wrap(self.GetOutput())


###############################################################################

class SlideSliceAlongPoints(ManySlicesAlongPoints):
    """Takes a series of points and a data source to be sliced. The points are
    used to construct a path through the data source and a slice is added at
    specified locations along that path along the vector of that path at that
    point. This constructs one slice through the input dataset which the user
    can translate via a slider bar in ParaView.

    Note:
        * Make sure the input data source is slice-able.
        * The SciPy module is required for this filter.
    """
    __displayname__ = 'Slide Slice Along Points'
    __category__ = 'filter'

    def __init__(self, n_slices=5, nearest_nbr=True):
        ManySlicesAlongPoints.__init__(self, outputType='vtkPolyData')
        self.__planes = None
        self.__loc = 50 # Percent (halfway)


    def _get_slice(self, pts, data, planes, output):
        """Internal helper to perfrom the filter
        """
        if not isinstance(planes, vtk.vtkPlane):
            raise _helpers.PVGeoError('``_get_slice`` can only handle one plane.')
        numPoints = pts.GetNumberOfPoints()
        # Set number of blocks based on user choice in the selction
        self._slice(data, output, planes)
        return output


    def RequestData(self, request, inInfo, outInfo):
        """Used by pipeline to generate output"""
        # Get input/output of Proxy
        pts = self.GetInputData(inInfo, 0, 0) # Port 0: points
        data = self.GetInputData(inInfo, 1, 0) # Port 1: sliceable data
        output = vtk.vtkPolyData.GetData(outInfo, 0)
        # Perfrom task
        if self.__planes is None or len(self.__planes) < 1:
            self.set_number_of_slices(pts.GetNumberOfPoints())
            self.__planes = self._get_planes(pts)
        idx = int(np.floor(pts.GetNumberOfPoints() * float(self.__loc / 100.0)))
        self._get_slice(pts, data, self.__planes[idx], output)
        return 1

    def RequestInformation(self, request, inInfo, outInfo):
        """Used by pipeline to prepare output"""
        pts = self.GetInputData(inInfo, 0, 0) # Port 0: points
        self.set_number_of_slices(pts.GetNumberOfPoints())
        self.__planes = self._get_planes(pts)
        return 1

    def set_location(self, loc):
        """Set the location along the input line for the slice location as a
        percent (0, 99)."""
        if (loc > 99 or loc < 0):
            raise _helpers.PVGeoError('Location must be given as a percentage along input path.')
        if self.__loc != loc:
            self.__loc = loc
            self.Modified()

    def get_location(self):
        """Return the current location along the input line for the slice"""
        return self.__loc


###############################################################################



class ManySlicesAlongAxis(_SliceBase):
    """Slices a ``vtkDataSet`` along a given axis many times.
    This produces a specified number of slices at once each with a normal vector
    oriented along the axis of choice and spaced uniformly through the range of
    the dataset on the chosen axis.

    Args:
        pad (float): Padding as a percentage (0.0, 1.0)
    """
    __displayname__ = 'Many Slices Along Axis'
    __category__ = 'filter'

    def __init__(self, n_slices=5, axis=0, rng=None, pad=0.01, outputType='vtkMultiBlockDataSet'):
        _SliceBase.__init__(self, n_slices=n_slices,
                            nInputPorts=1, inputType='vtkDataSet',
                            nOutputPorts=1, outputType=outputType)
        # Parameters
        self.__axis = axis
        self.__rng = rng
        self.__pad = pad


    def _get_origin(self, pdi, idx):
        """Internal helper to get plane origin
        """
        og = list(self.get_input_center(pdi))
        og[self.__axis] = self.__rng[idx]
        return og


    def get_input_bounds(self, pdi):
        """Gets the bounds of the input data set on the set slicing axis.
        """
        bounds = pdi.GetBounds()
        return bounds[self.__axis*2], bounds[self.__axis*2+1]

    @staticmethod
    def get_input_center(pdi):
        """Gets the center of the input data set

        Return:
            tuple: the XYZ coordinates of the center of the data set.
        """
        bounds = pdi.GetBounds()
        x = (bounds[1] + bounds[0])/2
        y = (bounds[3] + bounds[2])/2
        z = (bounds[5] + bounds[4])/2
        return (x, y, z)

    def get_normal(self):
        """Get the normal of the slicing plane"""
        norm = [0,0,0]
        norm[self.__axis] = 1
        return norm

    def _set_axial_range(self, pdi):
        """Internal helper to set the slicing range along the set axis
        """
        bounds = self.get_input_bounds(pdi)
        padding = (bounds[1] - bounds[0]) * self.__pad # get percent padding
        self.__rng = np.linspace(bounds[0]+padding, bounds[1]-padding, num=self.get_number_of_slices())


    def RequestData(self, request, inInfo, outInfo):
        """Used by pipeline to generate output
        """
        # Get input/output of Proxy
        pdi = self.GetInputData(inInfo, 0, 0)
        # Get output:
        #output = self.GetOutputData(outInfo, 0)
        output = vtk.vtkMultiBlockDataSet.GetData(outInfo, 0)
        self._set_axial_range(pdi)
        normal = self.get_normal()
        # Perfrom task
        # Set number of blocks based on user choice in the selction
        output.SetNumberOfBlocks(self.get_number_of_slices())
        blk = 0
        for i in range(self.get_number_of_slices()):
            temp = vtk.vtkPolyData()
            origin = self._get_origin(pdi, i)
            plane = self._generate_plane(origin, normal)
            # Perfrom slice for that index
            self._slice(pdi, temp, plane)
            output.SetBlock(blk, temp)
            output.GetMetaData(blk).Set(vtk.vtkCompositeDataSet.NAME(), 'Slice%.2d' % i)
            blk += 1

        return 1



    #### Getters / Setters ####


    def set_axis(self, axis):
        """Set the axis on which to slice

        Args:
            axis (int): the axial index (0, 1, 2) = (x, y, z)
        """
        if axis not in (0,1,2):
            raise _helpers.PVGeoError('Axis choice must be 0, 1, or 2 (x, y, or z)')
        if self.__axis != axis:
            self.__axis = axis
            self.Modified()

    def get_range(self):
        """Get the slicing range for the set axis
        """
        return self.__rng

    def get_axis(self):
        """Get the set axis to slice upon as int index (0,1,2)
        """
        return self.__axis

    def set_padding(self, pad):
        """Set the percent padding for the slices on the edges"""
        if self.__pad != pad:
            self.__pad = pad
            self.Modified()



###############################################################################


class SliceThroughTime(ManySlicesAlongAxis):
    """Takes a sliceable ``vtkDataSet`` and progresses a slice of it along a
    given axis. The macro requires that the clip already exist in the pipeline.
    This is especially useful if you have many clips linked together as all will
    move through the seen as a result of this macro.
    """
    __displayname__ = 'Slice Through Time'
    __category__ = 'filter'

    def __init__(self, n_slices=5, dt=1.0, axis=0, rng=None,):
        ManySlicesAlongAxis.__init__(self, n_slices=n_slices,
                                     axis=axis, rng=rng, outputType='vtkPolyData')
        # Parameters
        self.__dt = dt
        self.__timesteps = None

    def _update_time_steps(self):
        """For internal use only
        """
        self.__timesteps = _helpers.update_time_steps(self, self.get_number_of_slices(), self.__dt)

    #### Algorithm Methods ####

    def RequestData(self, request, inInfo, outInfo):
        """Used by pipeline to generate output
        """
        # Get input/output of Proxy
        pdi = self.GetInputData(inInfo, 0, 0)
        pdo = self.GetOutputData(outInfo, 0)
        self._set_axial_range(pdi)
        i = _helpers.get_requested_time(self, outInfo)
        # Perfrom task
        normal = self.get_normal()
        origin = self._get_origin(pdi, i)
        plane = self._generate_plane(origin, normal)
        self._slice(pdi, pdo, plane)
        return 1

    def RequestInformation(self, request, inInfo, outInfo):
        """Used by pipeline to set the time information
        """
        # register time:
        self._update_time_steps()
        return 1

    #### Public Getters / Setters ####

    def set_number_of_slices(self, num):
        """Set the number of slices/timesteps to generate
        """
        ManySlicesAlongAxis.set_number_of_slices(self, num)
        self._update_time_steps()
        self.Modified()

    def set_time_delta(self, dt):
        """
        Set the time step interval in seconds
        """
        if self.__dt != dt:
            self.__dt = dt
            self._update_time_steps()
            self.Modified()

    def get_time_step_values(self):
        """Use this in ParaView decorator to register timesteps
        """
        return self.__timesteps.tolist() if self.__timesteps is not None else None
