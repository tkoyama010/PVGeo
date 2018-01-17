import vtk
import numpy as np
from vtk.util import numpy_support as nps

#---- Reshape Table ----#

def reshapeTable(pdi, nrows, ncols, pdo=None):
    """
    Todo Description
    """
    if pdo is None:
        pdo = vtk.vtkTable()
    # Get number of columns
    cols = pdi.GetNumberOfColumns()
    # Get number of rows
    rows = pdi.GetColumn(0).GetNumberOfTuples() # TODO is the necessary?

    # Make a 2D numpy array and fille with data from input table
    data = np.empty((cols,rows))
    for i in range(cols):
        c = pdi.GetColumn(i)
        data[i] = nps.vtk_to_numpy(c)

    order = 'C'
    '''
    # Cannot use Fortran because nps needs contigous arrays
    if Fortran_Ordering:
        order = 'F'
    '''

    if ((ncols*nrows) != (cols*rows)):
        raise Exception('Total number of elements must remain %d. Check reshape dimensions.' % (cols*rows))

    # Use numpy.reshape() to reshape data NOTE: only 2D because its a table
    # NOTE: column access of this reshape is not contigous
    data = np.reshape(data, (nrows,ncols), order=order)
    pdo.SetNumberOfRows(nrows)

    # Add new array to output table and assign incremental names (e.g. Field0)
    for i in range(ncols):
        # Make a contigous array from the column we want
        col = np.array(data[:,i])
        # allow type to be determined by input
        insert = nps.numpy_to_vtk(num_array=col, deep=True) # array_type=vtk.VTK_FLOAT
        # VTK arrays need a name. Set arbitrarily
        insert.SetName('Field%d' % i)
        #pdo.AddColumn(insert) # these are not getting added to the output table
        # ... work around:
        pdo.GetRowData().AddArray(insert) # NOTE: this is in the FieldData

    return pdo
