'''
This is a module containing functions to construct an airfoil
'''
import copy

import numpy as np
from numpy.linalg import lstsq
from scipy import spatial
from scipy.interpolate import interp1d
from scipy.special import factorial

from .naca import naca

import matplotlib.pyplot as plt


class Section:
    '''
    Section 3D curve generated by CST foil (upper & lower surface)
    '''
    def __init__(self, thick=None, chord=1.0, twist=0.0, tail=0.0):
        self.xLE = 0.0
        self.yLE = 0.0
        self.zLE = 0.0
        self.chord = chord
        self.twist = twist
        self.thick = thick
        self.tail = tail
        self.RLE = 0.0

        #* 2D unit airfoil
        self.cst_u = np.zeros(1)
        self.cst_l = np.zeros(1)
        self.xx = np.zeros(1)
        self.yu = np.zeros(1)
        self.yl = np.zeros(1)

        #* 3D section
        self.x = np.zeros(1)
        self.y = np.zeros(1)
        self.z = np.zeros(1)

        #* Refine airfoil
        self.refine_fixed_t = True
        self.refine_u = None
        self.refine_l = None

    def set_params(self, init=False, **kwargs):
        '''
        Set parameters of the section \n

        Inputs:
        ---
        init:   True, set to default values \n

        kwargs:
        ---
        xLE, yLE, zLE, chord, twist, tail, thick (None) \n

        refine_fixed_t: True, fixed thickness when adding incremental curves \n
        refine_u:       ndarray, cst coefficients of upper incremental curve \n
        refine_l:       ndarray, cst coefficients of lower incremental curve \n
        '''
        if init:
            self.xLE = 0.0
            self.yLE = 0.0
            self.zLE = 0.0
            self.chord = 1.0
            self.thick = None
            self.twist = 0.0
            self.tail = 0.0

            self.refine_fixed_t = True
            self.refine_u = None
            self.refine_l = None
            return

        if 'xLE' in kwargs.keys():
            self.xLE = kwargs['xLE']

        if 'yLE' in kwargs.keys():
            self.yLE = kwargs['yLE']

        if 'zLE' in kwargs.keys():
            self.zLE = kwargs['zLE']

        if 'chord' in kwargs.keys():
            self.chord = kwargs['chord']

        if 'thick' in kwargs.keys():
            self.thick = kwargs['thick']

        if 'twist' in kwargs.keys():
            self.twist = kwargs['twist']

        if 'tail' in kwargs.keys():
            self.tail = kwargs['tail']

        if 'refine_fixed_t' in kwargs.keys():
            self.refine_fixed_t = kwargs['refine_fixed_t']

        if 'refine_u' in kwargs.keys():
            aa_ = kwargs['refine_u']
            if isinstance(aa_, np.ndarray):
                self.refine_u = aa_.copy()

        if 'refine_l' in kwargs.keys():
            aa_ = kwargs['refine_l']
            if isinstance(aa_, np.ndarray):
                self.refine_l = aa_.copy()

    def section(self, cst_u=None, cst_l=None, nn=1001, flip_x=False, proj=True):
        '''
        Generating the section (3D) by cst_foil. 

        ### Inputs:
        ```text
        nn:     total amount of points
        cst_u:  CST coefficients of upper surface (ndarray, optional)
        cst_l:  CST coefficients of lower surface (ndarray, optional)
        flip_x: True ~ flip section.xx in reverse order
        proj:   True => for unit airfoil, the rotation keeps the projection length the same
        ```
        '''
        if isinstance(cst_u, np.ndarray) and isinstance(cst_l, np.ndarray):
            self.cst_u = cst_u.copy()
            self.cst_l = cst_l.copy()

        self.xx, self.yu, self.yl, self.thick, self.RLE = cst_foil(
            nn, self.cst_u, self.cst_l, t=self.thick, tail=self.tail)

        #* Refine the airfoil by incremental curves
        if self.refine_fixed_t:
            t0 = self.thick
        else:
            t0 = None

        if (self.refine_u is not None) or (self.refine_l is not None):
            self.yu, self.yl = foil_increment(self.xx, self.yu, self.yl, self.refine_u, self.refine_l, t=t0)

        #* Transform to 3D
        if flip_x:
            self.xx.reverse()

        xu_, xl_, yu_, yl_ = transform(self.xx, self.xx, self.yu, self.yl, 
            scale=self.chord, rot=self.twist, dx=self.xLE, dy=self.yLE, proj=proj)

        self.x = np.concatenate((np.flip(xl_),xu_[1:]), axis=0)
        self.y = np.concatenate((np.flip(yl_),yu_[1:]), axis=0)
        self.z = np.ones(2*nn-1)*self.zLE

    def copyfrom(self, other):
        '''
        Copy from anthor section object
        '''
        if not isinstance(other, Section):
            raise Exception('Must copy from another section object')
        
        self.xLE = other.xLE
        self.yLE = other.yLE
        self.zLE = other.zLE
        self.chord = other.chord
        self.twist = other.twist
        self.thick = other.thick
        self.tail = other.tail
        self.RLE = other.RLE

        self.cst_u = other.cst_u.copy()
        self.cst_l = other.cst_l.copy()
        self.xx = other.xx.copy()
        self.yu = other.yu.copy()
        self.yl = other.yl.copy()

        self.x = other.x.copy()
        self.y = other.y.copy()
        self.z = other.z.copy()

        self.refine_fixed_t = other.refine_fixed_t
        self.refine_u = copy.deepcopy(other.refine_u)
        self.refine_l = copy.deepcopy(other.refine_l)


class OpenSection:
    '''
    Section 3D curve generated by CST curve (open curve)
    '''
    def __init__(self, thick=None, chord=1.0, twist=0.0):
        self.xLE = 0.0
        self.yLE = 0.0
        self.zLE = 0.0
        self.chord = chord
        self.twist = twist
        self.thick = thick

        #* 2D unit curve
        self.cst = np.zeros(1)
        self.xx  = np.zeros(1)
        self.yy  = np.zeros(1)

        #* 3D section
        self.x = np.zeros(1)
        self.y = np.zeros(1)
        self.z = np.zeros(1)

        #* Refine airfoil
        self.refine = None

    def set_params(self, init=False, **kwargs):
        '''
        Set parameters of the section \n

        Inputs:
        ---
        init:   True, set to default values \n

        kwargs:
        ---
        xLE, yLE, zLE, chord, twist, thick (None) \n
        refine: ndarray, cst coefficients of incremental curve \n
        '''
        if init:
            self.xLE = 0.0
            self.yLE = 0.0
            self.zLE = 0.0
            self.chord = 1.0
            self.twist = 0.0
            self.thick = None

            self.refine = None
            return

        if 'xLE' in kwargs.keys():
            self.xLE = kwargs['xLE']

        if 'yLE' in kwargs.keys():
            self.yLE = kwargs['yLE']

        if 'zLE' in kwargs.keys():
            self.zLE = kwargs['zLE']

        if 'chord' in kwargs.keys():
            self.chord = kwargs['chord']

        if 'twist' in kwargs.keys():
            self.twist = kwargs['twist']

        if 'refine' in kwargs.keys():
            aa_ = kwargs['refine']
            if isinstance(aa_, np.ndarray):
                self.refine = aa_.copy()

    def section(self, cst=None, nn=1001, flip_x=False, proj=True):
        '''
        Generating the section (3D) by cst_curve. 

        ### Inputs:
        ```text
        nn:     total amount of points
        cst:    CST coefficients of the curve (ndarray, optional)
        flip_x: True ~ flip section.xx in reverse order
        proj:   True => for unit airfoil, the rotation keeps the projection length the same
        ```
        '''
        if isinstance(cst, np.ndarray):
            self.cst = cst.copy()

        self.xx, self.yy = cst_curve(nn, self.cst)

        if isinstance(self.refine, np.ndarray):
            _, y_i = cst_curve(nn, self.refine, x=self.xx)
            self.yy += y_i

        #* Apply thickness
        if isinstance(self.thick, float):
            t0 = np.max(self.yy, axis=0)
            self.yy = self.yy/t0*self.thick

        #* Transform to 3D
        if flip_x:
            self.xx.reverse()

        self.x, _, self.y, _ = transform(self.xx, self.xx, self.yy, self.yy, 
            scale=self.chord, rot=self.twist, dx=self.xLE, dy=self.yLE, proj=proj)

        self.z = np.ones(nn)*self.zLE

    def copyfrom(self, other):
        '''
        Copy from anthor OpenSection object
        '''
        if not isinstance(other, OpenSection):
            raise Exception('Must copy from another OpenSection object')
        
        self.xLE = other.xLE
        self.yLE = other.yLE
        self.zLE = other.zLE
        self.chord = other.chord
        self.twist = other.twist

        self.cst = other.cst.copy()
        self.xx = other.xx.copy()
        self.yy = other.yy.copy()

        self.x = other.x.copy()
        self.y = other.y.copy()
        self.z = other.z.copy()

        self.refine = copy.deepcopy(other.refine)


#* ===========================================
#* Static functions
#* ===========================================

def cst_foil(nn, coef_upp, coef_low, x=None, t=None, tail=0.0):
    '''
    Constructing upper and lower curves of an airfoil based on CST method

    CST:    class shape transfermation method (Kulfan, 2008)

    >>> x_, yu, yl, t0, R0 = cst_foil()

    ### Inputs:
    ```text
    nn:         total amount of points
    coef_upp:   CST coefficients of upper surface (ndarray)
    coef_low:   CST coefficients of lower surface (ndarray)
    x:          point x [0,1] (optional ndarray, size is nn)
    t:          relative maximum thickness (optional)
    tail:       relative tail thickness (optional)
    ```

    ### Return
    x (ndarray), y_upp (ndarray), y_low (ndarray), t0, R0
    '''
    x_, yu = cst_curve(nn, coef_upp, x=x)
    x_, yl = cst_curve(nn, coef_low, x=x)
    
    thick = yu-yl
    it = np.argmax(thick)
    t0 = thick[it]

    # Apply thickness constraint
    if t is not None:
        r  = (t-tail*x_[it])/t0
        t0 = t
        yu = yu * r
        yl = yl * r

    # Add tail
    for i in range(nn):
        yu[i] += 0.5*tail*x_[i]
        yl[i] -= 0.5*tail*x_[i]

    # Calculate leading edge radius
    x_RLE = 0.005
    yu_RLE = interplot_from_curve(x_RLE, x_, yu)
    yl_RLE = interplot_from_curve(x_RLE, x_, yl)
    R0, _ = find_circle_3p([0.0,0.0], [x_RLE,yu_RLE], [x_RLE,yl_RLE])

    return x_, yu, yl, t0, R0

def cst_foil_fit(xu, yu, xl, yl, n_order=7):
    '''
    Using CST method to fit an airfoil

    This function allows the airfoil has non-zero tail thickness.
    Also allows the airfoil chord length not equals to one.

    >>> cst_u, cst_l = cst_foil_fit(xu, yu, xl, yl, n_order=7)

    ### Inputs:
    ```text
    xu, yu:  upper surface points (ndarray)
    xl, yl:  lower surface points (ndarray)
    n_order: number of CST parameters
    ```

    ### Return: 
    cst_u, cst_l (ndarray)
    '''
    cst_u = fit_curve(xu, yu, n_order=n_order)
    cst_l = fit_curve(xl, yl, n_order=n_order)
    return cst_u, cst_l

def foil_bump_modify(x, yu, yl, xc: float, h: float, s: float, side=1, n_order=0):
    '''
    Add bumps on the airfoil

    >>> yu_new, yl_new = foil_bump_modify(x, yu, yl, xc, h, s, side, n_order)

    ### Inputs:
    ```text
    x, yu, yl: current airfoil (ndarray)
    xc:        x of the bump center
    h:         relative height of the bump (to maximum thickness)
    s:         span of the bump
    side:      +1/-1 upper/lower side of the airfoil
    n_order:   if specified (>0), then use CST to fit the new foil
    ```

    ### Return:
    yu_new, yl_new (ndarray)
    '''
    yu_new = yu.copy()
    yl_new = yl.copy()
    t0 = np.max(yu_new-yl_new)

    yu_ = yu.copy()
    yl_ = yl.copy()

    if xc<0.1 or xc>0.9:
        kind = 'H'
    else:
        kind = 'G'

    if side > 0:
        yu_new = add_bump(x, yu_new, xc, h*t0, s, kind=kind)
    else:
        yl_new = add_bump(x, yl_new, xc, h*t0, s, kind=kind)

    it = np.argmax(yu_new-yl_new)
    tu = np.abs(yu_new[it])
    tl = np.abs(yl_new[it])

    if side > 0:
        rl = (t0-tu)/tl
        yl_new = rl * np.array(yl_new)
    else:
        ru = (t0-tl)/tu
        yu_new = ru * np.array(yu_new)

    if n_order > 0:
        # CST reverse
        tail = yu[-1] - yl[-1]

        c_upp, c_low = cst_foil_fit(x, yu_new, x, yl_new, n_order=n_order)
        _, yu_new, yl_new, _, _ = cst_foil(len(x),c_upp,c_low,x=x, t=t0,tail=tail)

    return yu_new, yl_new

def foil_tcc(x, yu, yl, info=True):
    '''
    Calculate thickness, curvature, camber distribution.

    >>> thickness, curv_u, curv_l, camber = foil_tcc(x, yu, yl, info=True)

    ### Inputs:
    ```text
    x, yu, yl: current airfoil (ndarray)
    ```

    ### Return: 
    thickness, curv_u, curv_l, camber (ndarray)
    '''
    curv_u = curve_curvature(x, yu)
    curv_l = curve_curvature(x, yl)

    thickness = yu-yl
    camber = 0.5*(yu+yl)
    for i in range(x.shape[0]):
        if info and thickness[i]<0:
            print('Unreasonable Airfoil: negative thickness')

    return thickness, curv_u, curv_l, camber

def check_valid(x, yu, yl, RLE=0.0, neg_tcri=0.0) -> list:
    '''
    Check if the airfoil is reasonable by rules

    >>> rule_invalid = check_valid(x, yu, yl, RLE=0.0)

    ### Inputs:
    ```text
    x, yu, yl: current airfoil (ndarray)
    RLE:       The leading edge radius of this airfoil
    neg_tcri:  critical value for checking negative thickness
               e.g., neg_tcri = -0.01, then only invalid when the thickness is smaller than -0.01
    ```

    ### Rules:
    ```text
    1:  negative thickness
    2:  maximum thickness point location
    3:  extreme points of thickness
    4:  maximum curvature
    5:  maximum camber within x [0.2,0.7]
    6:  RLE if provided
    7:  convex LE
    ```

    ### Return:
    rule_invalid: list, 0 means valid
    '''
    thickness, curv_u, curv_l, camber = foil_tcc(x, yu, yl, info=False)
    nn = x.shape[0]

    n_rule = 10
    rule_invalid = [0 for _ in range(n_rule)]

    #* Rule 1: negative thickness
    if np.min(thickness) < neg_tcri:
        rule_invalid[0] = 1

    #* Rule 2: maximum thickness point location
    i_max = np.argmax(thickness)
    t0    = thickness[i_max]
    x_max = x[i_max]
    if x_max<0.15 or x_max>0.75:
        rule_invalid[1] = 1

    #* Rule 3: extreme points of thickness
    n_extreme = 0
    for i in range(nn-2):
        a1 = thickness[i+2]-thickness[i+1]
        a2 = thickness[i]-thickness[i+1]
        if a1*a2>=0.0:
            n_extreme += 1
    if n_extreme>2:
        rule_invalid[2] = 1

    #* Rule 4: maximum curvature
    cur_max_u = 0.0
    cur_max_l = 0.0
    for i in range(nn):
        if x[i]<0.1:
            continue
        cur_max_u = max(cur_max_u, abs(curv_u[i]))
        cur_max_l = max(cur_max_l, abs(curv_l[i]))

    if cur_max_u>5 or cur_max_l>5:
        rule_invalid[3] = 1

    #* Rule 5: Maximum camber within x [0.2,0.7]
    cam_max = 0.0
    for i in range(nn):
        if x[i]<0.2 or x[i]>0.7:
            continue
        cam_max = max(cam_max, abs(camber[i]))

    if cam_max>0.025:
        rule_invalid[4] = 1
    
    #* Rule 6: RLE
    if RLE>0.0 and RLE<0.005:
        rule_invalid[5] = 1

    if RLE>0.0 and RLE/t0<0.01:
        rule_invalid[5] = 1

    #* Rule 7: convex LE
    ii = int(0.1*nn)+1
    a0 = thickness[i_max]/x[i_max]
    au = yu[ii]/x[ii]/a0
    al = -yl[ii]/x[ii]/a0

    if au<1.0 or al<1.0:
        rule_invalid[6] = 1
    
    #if sum(rule_invalid)<=0:
    #    np.set_printoptions(formatter={'float': '{: 0.6f}'.format}, linewidth=100)
    #    print(np.array([x_max, n_extreme, cur_max_u, cur_max_l, cam_max, RLE/t0, au, al]))

    return rule_invalid

def foil_increment(x, yu, yl, coef_upp, coef_low, t=None):
    '''
    Add cst curve by incremental curves

    >>> yu_, yl_ = foil_increment(x, yu, yl, coef_upp, coef_low, t=None)

    ### Inputs:
    ```text
    x, yu, yl:  baseline airfoil (ndarray)
    coef_upp:   CST coefficients of incremental upper curve (ndarray or None)
    coef_low:   CST coefficients of incremental lower curve (ndarray or None)
    t:          relative maximum thickness (optional)
    ```

    ### Return: 
    y_upp, y_low (ndarray)
    '''
    nn = len(x)

    if coef_upp is not None:
        _, yu_i = cst_curve(nn, coef_upp, x=x)
    else:
        yu_i = np.zeros(nn)

    if coef_upp is not None:
        _, yl_i = cst_curve(nn, coef_low, x=x)
    else:
        yl_i = np.zeros(nn)

    x_   = x.copy()
    yu_  = yu.copy()
    yl_  = yl.copy()

    # Remove tail
    tail = yu_[-1] - yl_[-1]
    if tail > 0.0:
        yu_ = yu_ - 0.5*tail*x_
        yl_ = yl_ + 0.5*tail*x_

    # Add incremental curves
    yu_  = yu_ + yu_i
    yl_  = yl_ + yl_i

    thick = yu_-yl_
    it = np.argmax(thick)
    t0 = thick[it]

    # Apply thickness constraint
    if t is not None:
        r  = (t-tail*x[it])/t0
        yu_ = yu_ * r
        yl_ = yl_ * r

    # Add tail
    if tail > 0.0:
        yu_ = yu_ + 0.5*tail*x_
        yl_ = yl_ - 0.5*tail*x_

    return yu_, yl_

def naca_to_cst(NACA_series: str, n_order=7, nn=101):
    '''
    Get CST parameters of a NACA series airfoil

    >>> cst_u, cst_l = naca_to_cst(NACA_series, n_order, nn)

    ### Inputs:
    ```text
    NACA_series:    4 or 5 digit NACA number string
    n_order:        number of CST parameters
    nn:             total amount of points
    ```

    ### Return: 
    cst_u, cst_l (ndarray)
    '''
    xx, yy = naca(NACA_series, nn-1, finite_TE=False, half_cosine_spacing=True)

    xu = np.zeros(nn)
    xl = np.zeros(nn)
    yu = np.zeros(nn)
    yl = np.zeros(nn)

    n0 = 2*nn-1
    for i in range(nn):
        xu[i] = xx[n0-i-nn]
        yu[i] = yy[n0-i-nn]
        xl[i] = xx[nn+i-1]
        yl[i] = yy[nn+i-1]

    cst_u, cst_l = cst_foil_fit(xu, yu, xl, yl, n_order=n_order)

    return cst_u, cst_l

def scale_cst(x, yu, yl, cst_u, cst_l, t: float, tail=0.0):
    '''
    Scale CST coefficients, so that the airfoil has the maximum thickness of t. 

    >>> cst_u_new, cst_l_new = scale_cst(yu, yl, cst_u, cst_l, t)

    ### Inputs:
    ```text
    x, yu, yl:      baseline airfoil (ndarray)
                    x, yu, yl must be directly generated by CST, without scaling
    cst_u, cst_l:   CST coefficients (ndarray)
    t:              target thickness
    tail:           relative tail thickness (optional)
    ```
    '''

    thick = yu - yl
    it = np.argmax(thick)
    t0 = thick[it]

    r  = (t-tail*x[it])/t0
    cst_u_new = cst_u * r
    cst_l_new = cst_l * r

    return cst_u_new, cst_l_new

def fromCylinder(x, y, z, flip=True):
    '''
    Bend the cylinder curve to a 2D plane curve.

    ### Inputs:
    ```text
    x, y ,z: point coordinate ndarray of curves on the cylinder
    ```

    ### Return:
    X, Y, Z: point coordinate ndarray of curves bent to 2D X-Y planes

    ### Note:
    ```text
    Cylinder: origin (0,0,0), axis is z-axis
    x and y must not be 0 at the same time

    The origin of cylinder and plane curves is the same (0,0,0).
    
        Cylinder: x, y, z ~~ r, theta, z
        Plane:    X, Y, Z

        theta = arctan(y/x)
        r = sqrt(x^2+y^2)
        z = z

        X = r*theta
        Y = z
        Z = r
    ```
    '''
    coef = -1.0 if flip else 1.0

    rr = np.sqrt(x*x+y*y)
    tt = np.arctan2(y, x) * coef

    X = rr*tt
    Y = z.copy()
    Z = rr

    return X, Y, Z

def toCylinder(X, Y, Z, flip=True):
    '''
    Bend the plane sections to curves on a cylinder.

    ### Inputs:
    ```text
    X, Y, Z: point coordinate ndarray of curves on 2D X-Y planes
    Z must not be 0
    ```

    ### Return:
    x, y ,z: point coordinate ndarray of curves bent to a cylinder

    ### Note:
    ```text
    The origin of cylinder and plane curves is the same (0,0,0).
    
        Plane:    X, Y, Z
        Cylinder: x, y, z ~~ r, theta, z
        
        theta = arctan(y/x)
        r = sqrt(x^2+y^2)
        z = z

        X = r*theta
        Y = z
        Z = r
    ```
    '''
    coef = -1.0 if flip else 1.0

    nn = X.shape[0]
    x = np.zeros(nn)
    y = np.zeros(nn)
    z = Y.copy()

    for i in range(nn):
        r = Z[i]
        theta = X[i]/r * coef
        x[i] = r*np.cos(theta)
        y[i] = r*np.sin(theta)

    return x, y, z

#* ===========================================
#* Supportive functions
#* ===========================================

def clustcos(i: int, nn: int, a0=0.0079, a1=0.96, beta=1.0) -> float:
    '''
    Point distribution on x-axis [0, 1]. (More points at both ends)

    >>> c = clustcos(i, n, a0, a1, beta)

    ### Inputs:
    ```text
    i:      index of current point (start from 0)
    nn:     total amount of points
    a0:     parameter for distributing points near x=0
    a1:     parameter for distributing points near x=1
    beta:   parameter for distribution points 
    ```
    '''
    aa = np.power((1-np.cos(a0*np.pi))/2.0, beta)
    dd = np.power((1-np.cos(a1*np.pi))/2.0, beta) - aa
    yt = i/(nn-1.0)
    a  = np.pi*(a0*(1-yt)+a1*yt)
    c  = (np.power((1-np.cos(a))/2.0,beta)-aa)/dd

    return c

def cst_curve(nn: int, coef, x=None, xn1=0.5, xn2=1.0):
    '''
    Generating single curve based on CST method.

    CST:    class shape transfermation method (Kulfan, 2008)

    >>> x, y = cst_curve(nn, coef, x, xn1, xn2)

    ### Inputs:
    ```text
    nn:     total amount of points
    coef:   CST coefficients (ndarray)
    x:      points x [0,1] (optional ndarray, size= nn)
    xn1,2:  CST parameters
    ```
    ### Return:
    x, y (ndarray)
    '''
    if x is None:
        x = np.zeros(nn)
        for i in range(nn):
            x[i] = clustcos(i, nn)
    elif x.shape[0] != nn:
        raise Exception('Specified point distribution has different size %d as input nn %d'%(x.shape[0], nn))
    
    n_order = coef.shape[0]
    y = np.zeros(nn)
    for ip in range(nn):
        s_psi = 0.0
        for i in range(n_order):
            xk_i_n = factorial(n_order-1)/factorial(i)/factorial(n_order-1-i)
            s_psi += coef[i]*xk_i_n * np.power(x[ip],i) * np.power(1-x[ip],n_order-1-i)

        C_n1n2 = np.power(x[ip],xn1) * np.power(1-x[ip],xn2)
        y[ip] = C_n1n2*s_psi

    y[0] = 0.0
    y[-1] = 0.0

    return x, y

def find_circle_3p(p1, p2, p3):
    '''
    Determine the radius and origin of a circle by 3 points (2D)

    >>> R, XC = find_circle_3p(p1, p2, p3)

    ### Inputs:
    ```text
    p1, p2, p3: [x, y], list or ndarray
    ```

    ### Return: 
    R, XC = np.array([xc, yc])
    '''
    x21 = p2[0] - p1[0]
    y21 = p2[1] - p1[1]
    x32 = p3[0] - p2[0]
    y32 = p3[1] - p2[1]

    if x21 * y32 - x32 * y21 == 0:
        raise Exception('Finding circle: 3 points in one line')

    xy21 = p2[0]*p2[0] - p1[0]*p1[0] + p2[1]*p2[1] - p1[1]*p1[1]
    xy32 = p3[0]*p3[0] - p2[0]*p2[0] + p3[1]*p3[1] - p2[1]*p2[1]
    
    y0 = (x32 * xy21 - x21 * xy32) / 2 * (y21 * x32 - y32 * x21)
    x0 = (xy21 - 2 * y0 * y21) / (2.0 * x21)
    R = np.sqrt(np.power(p1[0]-x0,2) + np.power(p1[1]-y0,2))

    return R, np.array([x0, y0])

def curve_curvature(x, y):
    '''
    Calculate curvature of points in the curve

    >>> curv = curve_curvature(x, y)

    ### Inputs:
    ```text
    x, y: points of curve (ndarray)
    ```

    Return: curv (ndarray)
    '''
    nn = x.shape[0]
    if nn<3:
        raise Exception('curvature needs at least 3 points')
    
    curv = np.zeros(nn)
    for i in range(1, nn-1):
        X1 = np.array([x[i-1], y[i-1]])
        X2 = np.array([x[i  ], y[i  ]])
        X3 = np.array([x[i+1], y[i+1]])

        a = np.linalg.norm(X1-X2)
        b = np.linalg.norm(X2-X3)
        c = np.linalg.norm(X3-X1)
        p = 0.5*(a+b+c)
        t = p*(p-a)*(p-b)*(p-c)
        R = a*b*c
        if R <= 1.0E-12:
            curv_ = 0.0
        else:
            curv_ = 4.0*np.sqrt(t)/R

        a1 = X2[0] - X1[0]
        a2 = X2[1] - X1[1]
        b1 = X3[0] - X1[0]
        b2 = X3[1] - X1[1]
        if a1*b2 < a2*b1:
            curv_ = -curv_

        curv[i] = curv_

    curv[0] = curv[1]
    curv[-1] = curv[-2]

    return curv

def transform(xu, xl, yu, yl, scale=1.0, rot=None, x0=None, y0=None, dx=0.0, dy=0.0, proj=False):
    '''
    Apply chord length, twist angle(deg) and leading edge position to unit airfoil

    >>> xu_new, xl_new, yu_new, yl_new = transform()

    ### Inputs:
    ```text
    xu, xl, yu, yl:  current curve or unit airfoil (ndarray)
    scale:      scale factor, e.g., chord length
    rot:        rotate angle (deg), +z direction for x-y plane, e.g., twist angle
    x0, y0:     rotation center (scaler)
    dx, dy:     translation, e.g., leading edge location
    proj:       True => for unit airfoil, the rotation keeps the projection length the same
    ```

    ### Return: 
    xu_new, xl_new, yu_new, yl_new (ndarray)
    '''
    #* Translation
    xu_new = dx + xu
    xl_new = dx + xl
    yu_new = dy + yu
    yl_new = dy + yl

    #* Rotation center
    if x0 is None:
        x0 = xu_new[0]
    if y0 is None:
        y0 = 0.5*(yu_new[0]+yl_new[0])
    
    #* Scale (keeps the same projection length)
    rr = 1.0
    if proj and not rot is None:
        angle = rot/180.0*np.pi  # rad
        rr = np.cos(angle)

    xu_new = x0 + (xu_new-x0)*scale/rr
    xl_new = x0 + (xl_new-x0)*scale/rr
    yu_new = y0 + (yu_new-y0)*scale/rr
    yl_new = y0 + (yl_new-y0)*scale/rr

    #* Rotation
    if not rot is None:
        xu_new, yu_new, _ = rotate(xu_new, yu_new, None, angle=rot, origin=[x0, y0, 0.0], axis='Z')
        xl_new, yl_new, _ = rotate(xl_new, yl_new, None, angle=rot, origin=[x0, y0, 0.0], axis='Z')

    return xu_new, xl_new, yu_new, yl_new

def rotate(x, y, z, angle=0.0, origin=[0.0, 0.0, 0.0], axis='X'):
    '''
    Rotate the 3D curve according to origin

    >>> x_, y_, z_ = rotate(x, y, z, angle, origin, axis)

    ### Inputs:
    ```text
    x,y,z:  curve ndarray
    angle:  rotation angle (deg)
    origin: rotation origin
    axis:   rotation axis (use positive direction to define angle)
    ```

    ### Return:
    x_, y_, z_ (ndarray)
    '''
    cc = np.cos( angle/180.0*np.pi )
    ss = np.sin( angle/180.0*np.pi )
    x_ = copy.deepcopy(x)
    y_ = copy.deepcopy(y)
    z_ = copy.deepcopy(z)

    if axis in 'X':
        y_ = origin[1] + (y-origin[1])*cc - (z-origin[2])*ss
        z_ = origin[2] + (y-origin[1])*ss + (z-origin[2])*cc

    if axis in 'Y':
        z_ = origin[2] + (z-origin[2])*cc - (x-origin[0])*ss
        x_ = origin[0] + (z-origin[2])*ss + (x-origin[0])*cc

    if axis in 'Z':
        x_ = origin[0] + (x-origin[0])*cc - (y-origin[1])*ss
        y_ = origin[1] + (x-origin[0])*ss + (y-origin[1])*cc

    return x_, y_, z_

def interplot_from_curve(x0, x, y) -> np.ndarray:
    '''
    Interplot points from curve represented points [x, y]

    >>> y0 = interplot_from_curve(x0, x, y)

    ### Inputs:
    ```text
    x0  : ndarray/value of x locations to be interploted
    x, y: points of curve (ndarray)
    ```

    ### Return: 
    y0: ndarray/float
    '''
    f  = interp1d(x, y, kind='cubic')
    y0 = f(x0)

    return y0

def curve_intersect(x1, y1, x2, y2):
    '''
    Find the intersect index between two curves.

    >>> i1, i2, points = curve_intersect(x1, y1, x2, y2)

    ### Inputs:
    ```text
    x1, y1: curve 1 coordinates, list or ndarray
    x2, y2: curve 2 coordinates, list or ndarray
    ```

    ### Return:
    ```text
    i1, i2: index of the closest points in curve 1 & 2
    points: tuple of two closest points in curve 1 & 2
    ```
    '''

    arr1 = np.vstack((np.array(x1),np.array(y1))).T
    arr2 = np.vstack((np.array(x2),np.array(y2))).T

    tree = spatial.KDTree(arr2)
    distance, arr2_index = tree.query(arr1)
    i1 = distance.argmin()  # type: int
    i2 = arr2_index[i1]     # type: int
    points = (arr1[i1], arr2[i2])

    return i1, i2, points

def stretch_fixed_point(x, y, dx=0.0, dy=0.0, xm=None, ym=None, xf=None, yf=None):
    '''
    Linearly stretch a curve when certain point is fixed

    >>> x_, y_ = stretch_fixed_point(x, y, dx, dy, xm, ym, xf, yf)

    ### Inputs:
    ```text
    x, y:   curve (ndarray)
    dx, dy: movement of the first element (scaler)
    xm, ym: The point that moves dx, dy (e.g., the first element of the curve)
    xf, yf: The fixed point (e.g., the last element of the curve)
    ```

    ### Returns:
    x_, y_ (ndarray)
    '''
    x_ = x.copy()
    y_ = y.copy()

    if xf is None or yf is None:
        xf = x[-1]
        yf = y[-1]

    if xm is None or ym is None:
        xm = x[0]
        ym = y[0]

    lm = np.linalg.norm([xm-xf, ym-yf])

    for i in range(x.shape[0]):
        rr  = np.linalg.norm([x[i]-xf, y[i]-yf]) / lm
        x_[i] = x_[i] + rr*dx
        y_[i] = y_[i] + rr*dy

    return x_, y_

def add_bump(x, y, xc: float, h: float, s: float, kind='G'):
    '''
    Add a bump on current curve [x, y]

    >>> y_new = add_bump(x, y, xc, h, s, kind)

    ### Inputs:
    ```text
    x, y:   current curve (ndarray, x[0,1])
    xc:     x of the bump center
    h:      height of the bump
    s:      span of the bump
    kind:   bump function
     'G':   Gaussian, less cpu cost
     'H':   Hicks-Henne, better when near leading edge
    ```

    ### Return: 
    y_new (ndarray, new curve)
    '''
    y_new = y.copy()

    if xc<=0 or xc>=1:
        print('Bump location not valid (0,1): xc = %.3f'%(xc))
        return y_new

    if 'G' in kind:

        for i in range(x.shape[0]):
            if xc-s<0.0 and x[i]<xc:
                sigma = xc/3.5
            elif  xc+s>1.0 and x[i]>xc:
                sigma = (1.0-xc)/3.5
            else:
                sigma = s/6.0
            aa = -np.power(x[i]-xc,2)/2.0/sigma**2
            y_new[i] += h*np.exp(aa)

    else:
        
        s0 = np.log(0.5)/np.log(xc) 

        Pow = 1
        span = 1.0
        hm = np.abs(h)
        while Pow<100 and span>s:
            x1  = -1.0
            x2  = -1.0
            for i in range(0, 201):
                xx = i*0.005
                rr = np.pi*np.power(xx,s0)
                yy = hm * np.power(np.sin(rr),Pow)
                if yy > 0.01*hm and x1<0.0 and xx<xc:
                    x1 = xx
                if yy < 0.01*hm and x2<0.0 and xx>xc:
                    x2 = xx
            if x2 < 0.0:
                x2 = 1.0
            
            span = x2 - x1
            Pow = Pow + 1

        for i in range(len(x)):
            rr = np.pi*np.power(x[i],s0)
            dy = h*np.power(np.sin(rr),Pow)
            y_new[i] += dy

    return y_new

def fit_curve(x, y, n_order=7, xn1=0.5, xn2=1.0):
    '''
    Using least square method to fit a CST curve

    >>> coef = fit_curve(x, y, n_order, xn1, xn2)

    ### Input:
    ```text
    x, y:    curve points (ndarray)
    n_order: number of CST parameters
    ```

    ### Attributes:
    ```text
    Array A: A[nn, n_order], nn=len(x)
    Array b: b[nn]
    ```

    ### Return: 
    coef (ndarray)
    '''
    nn = x.shape[0]
    L  = x[-1] - x[0]   # type: float
    x_ = (x-x[0])/L     # scaling x to 0~1
    b  = y.copy()
    for ip in range(nn):
        b[ip] -= x_[ip]*y[-1]   # removing tail

    A = np.zeros((nn, n_order))
    for ip in range(nn):
        C_n1n2 = np.power(x_[ip],xn1) * np.power(1-x_[ip],xn2)
        for i in range(n_order):
            xk_i_n = factorial(n_order-1)/factorial(i)/factorial(n_order-1-i)
            A[ip][i] = xk_i_n * np.power(x_[ip],i) * np.power(1-x_[ip],n_order-1-i) * C_n1n2

    solution = lstsq(A, b, rcond=None)

    return solution[0]

def fit_curve_with_twist(x, y, n_order=7, xn1=0.5, xn2=1.0):
    '''
    Using least square method to fit a CST curve

    >>> coef, chord, twist = fit_curve_with_twist(x, y, n_order, xn1, xn2)

    ### Input:
    ```text
    x, y:    curve points (ndarray)
    n_order: number of CST parameters
    ```

    ### Attributes:
    ```text
    Array A: A[nn, n_order], nn=len(x)
    Array b: b[nn]
    ```

    ### Return: 
    coef:   CST parameters, ndarray
    chord:  distance between two ends of the curve
    twist:  degree, +z axis
    '''
    chord = np.sqrt((x[0]-x[-1])**2+(y[0]-y[-1])**2)
    twist = np.arctan((y[-1]-y[0])/(x[-1]-x[0]))*180/np.pi

    x_ = (x - x[0])/chord
    y_ = (y - y[0])/chord
    x_, y_, _ = rotate(x_, y_, None, angle=-twist, axis='Z')

    coef = fit_curve(x_, y_, n_order=n_order, xn1=xn1, xn2=xn2)

    return coef, chord, twist

def output_foil(x, yu, yl, fname='airfoil.dat', ID=0, info=False):
    '''
    Output airfoil data to tecplot ASCII format file

    ### Inputs:
    ```text
    x, yu, yl:  current airfoil (ndarray)
    ID:         >0 append to existed file. 0: write header
    info:       True: include curvature, thickness and camber
    ```
    '''
    nn = x.shape[0]
    curv_u = np.zeros(nn)
    curv_l = np.zeros(nn)
    camber = np.zeros(nn)
    thickness = np.zeros(nn)
    
    if ID == 0:
        # Write header
        with open(fname, 'w') as f:
            if info: 
                line = 'Variables= X  Y  Curvature Thickness Camber \n '
            else:
                line = 'Variables= X  Y  \n '
            f.write(line)

    if info:
        thickness, curv_u, curv_l, camber = foil_tcc(x, yu, yl, info=info)

    with open(fname, 'a') as f:
        f.write('zone T="Upp-%d" i= %d \n'%(ID, nn))
        for i in range(nn):
            line = '   %.9f  %.9f'%(x[i], yu[i])
            if info:
                line = line + '  %.9f  %.9f  %.9f'%(curv_u[i], thickness[i], camber[i])
            f.write(line+'\n')
            
        f.write('zone T="Low-%d" i= %d \n'%(ID, nn))
        for i in range(nn):
            line = '   %.9f  %.9f'%(x[i], yl[i])
            if info:
                line = line + '  %.9f  %.9f  %.9f'%(curv_l[i], thickness[i], camber[i])
            f.write(line+'\n')













