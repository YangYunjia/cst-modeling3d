'''
Construct airfoil with CST
'''
import copy
import numpy as np
from numpy.linalg import lstsq

from scipy.special import factorial

from .naca import naca
from .basic import BasicSection, rotate, interplot_basic_sec, interplot_from_curve

#!---------------------------------------------------
#! For compatibility with v1
from .basic import intersect_point, transform, fromCylinder, toCylinder
#!---------------------------------------------------


#* ===========================================
#* CST sections
#* ===========================================

class Section(BasicSection):
    '''
    Section 3D curve generated by CST foil (upper & lower surface)
    '''
    def __init__(self, thick=None, chord=1.0, twist=0.0, tail=0.0):

        super().__init__(thick=thick, chord=chord, twist=twist)

        self.tail = tail
        self.RLE = 0.0
        
        self.te_angle = 0.0     # trailing edge angle (degree)
        self.te_slope = 0.0     # slope of the mean camber line at trailing edge (dy/dx)

        #* 2D unit airfoil
        self.cst_u = np.zeros(1)
        self.cst_l = np.zeros(1)

        #* Refine airfoil
        self.refine_u = None
        self.refine_l = None

    def set_params(self, init=False, **kwargs):
        '''
        Set parameters of the section

        ### Inputs:
        ```text
        init:   True, set to default values
        ```

        ### kwargs:
        ```text
        xLE, yLE, zLE, chord, twist, tail, thick (None)

        refine_u:       ndarray, cst coefficients of upper incremental curve
        refine_l:       ndarray, cst coefficients of lower incremental curve
        ```
        '''
        if init:
            super().set_params(init=True)

            self.tail = 0.0
            self.RLE  = 0.0

            self.refine_u = None
            self.refine_l = None
            return

        super().set_params(init=False, **kwargs)

        if 'tail' in kwargs.keys():
            self.tail = kwargs['tail']

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

        ### Functions:
        ```text
        1. Construct 2D unit curve (null in the BasicSection)
        2. Transform to 3D curve
        ```

        ### Inputs:
        ```text
        nn:     total amount of points
        cst_u:  CST coefficients of upper surface (ndarray, optional)
        cst_l:  CST coefficients of lower surface (ndarray, optional)
        flip_x: True ~ flip section.xx in reverse order
        proj:   True => for unit airfoil, the rotation keeps the projection length the same
        ```
        '''
        #* Update CST parameters
        if isinstance(cst_u, np.ndarray) and isinstance(cst_l, np.ndarray):
            self.cst_u = cst_u.copy()
            self.cst_l = cst_l.copy()

        #* Construct airfoil with CST parameters
        self.xx, self.yu, self.yl, self.thick, self.RLE = cst_foil(
            nn, self.cst_u, self.cst_l, t=self.thick_set, tail=self.tail)
        
        #* Trailing edge information
        a1 = [self.xx[-1]-self.xx[-5], self.yu[-1]-self.yu[-5]]
        a2 = [self.xx[-1]-self.xx[-5], self.yl[-1]-self.yl[-5]]
        self.te_angle = np.arccos(np.dot(a1,a2)/np.linalg.norm(a1)/np.linalg.norm(a2))/np.pi*180.0
        self.te_slope = 0.5*((self.yu[-1]+self.yl[-1])-(self.yu[-5]+self.yl[-5]))/(self.xx[-1]-self.xx[-5])

        #* Refine the airfoil by incremental curves
        yu_i = np.zeros(nn)
        yl_i = np.zeros(nn)

        if isinstance(self.refine_u, np.ndarray):
            _, y_tmp = cst_curve(nn, self.refine_u, x=self.xx)
            yu_i += y_tmp

        if isinstance(self.refine_l, np.ndarray):
            _, y_tmp = cst_curve(nn, self.refine_l, x=self.xx)
            yl_i += y_tmp

        self.yu, self.yl = foil_increment_curve(self.xx, self.yu, self.yl, yu_i=yu_i, yl_i=yl_i, t=self.thick_set)

        #* Transform to 3D
        super().section(flip_x=flip_x, proj=proj)

    def copyfrom(self, other):
        '''
        Copy from anthor section object
        '''
        if not isinstance(other, Section):
            raise Exception('Must copy from another section object')
        
        super().copyfrom(other)

        self.tail = other.tail
        self.RLE = other.RLE

        self.cst_u = other.cst_u.copy()
        self.cst_l = other.cst_l.copy()

        self.refine_u   = copy.deepcopy(other.refine_u)
        self.refine_l   = copy.deepcopy(other.refine_l)


class OpenSection(BasicSection):
    '''
    Section 3D curve generated by CST curve (open curve)
    '''
    def __init__(self, thick=None, chord=1.0, twist=0.0):

        super().__init__(thick=thick, chord=chord, twist=twist)

        #* 2D unit curve
        self.cst = np.zeros(1)

        #* Refine airfoil
        self.refine = None

        #* Round tail
        self.cst_flip = None

    def set_params(self, init=False, **kwargs):
        '''
        Set parameters of the section

        ### Inputs:
        ```text
        init:   True, set to default values
        ```

        ### kwargs:
        ```text
        xLE, yLE, zLE, chord, twist, thick (None)
        refine:     ndarray, cst coefficients of incremental curve
        cst_flip:   ndarray, cst coefficients of flipped incremental curve
        ```
        '''
        if init:
            super().set_params(init=True)
 
            self.refine = None
            return
        
        super().set_params(init=False, **kwargs)

        if 'refine' in kwargs.keys():
            aa_ = kwargs['refine']
            if isinstance(aa_, np.ndarray):
                self.refine = aa_.copy()

        if 'cst_flip' in kwargs.keys():
            aa_ = kwargs['cst_flip']
            if isinstance(aa_, np.ndarray):
                self.cst_flip = aa_.copy()

    def section(self, cst=None, nn=1001, flip_x=False, proj=True):
        '''
        Generating the section (3D) by cst_curve. 

        ### Functions:
        ```text
        1. Construct 2D unit curve (null in the BasicSection)
        2. Transform to 3D curve
        ```

        ### Inputs:
        ```text
        nn:     total amount of points
        cst:    CST coefficients of the curve (ndarray, optional)
        flip_x: True ~ flip section.xx in reverse order
        proj:   True => for unit airfoil, the rotation keeps the projection length the same
        ```
        '''
        #* Update CST parameters
        if isinstance(cst, np.ndarray):
            self.cst = cst.copy()

        #* Construct curve with CST parameters
        self.xx, self.yy = cst_curve(nn, self.cst)

        #* Refine the geometry with an incremental curve
        if isinstance(self.refine, np.ndarray):
            _, y_i = cst_curve(nn, self.refine, x=self.xx)
            self.yy += y_i

        #* Add round tail with an incremental curve
        if isinstance(self.cst_flip, np.ndarray):
            _, y_i = cst_curve(nn, self.cst_flip, x=1.0-self.xx)
            self.yy += y_i

        #* Apply thickness
        self.thick = np.max(self.yy, axis=0)
        if isinstance(self.thick_set, float):
            self.yy = self.yy/self.thick*self.thick_set
            self.thick = self.thick_set

        #* Transform to 3D
        super().section(flip_x=flip_x, proj=proj)

    def copyfrom(self, other):
        '''
        Copy from anthor OpenSection object
        '''
        if not isinstance(other, OpenSection):
            raise Exception('Must copy from another OpenSection object')

        super().copyfrom(other)

        self.cst = other.cst.copy()

        self.refine   = copy.deepcopy(other.refine)
        self.cst_flip = copy.deepcopy(other.cst_flip)


#* ===========================================
#* Foil functions
#* ===========================================

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

def check_valid(x, yu, yl, RLE=0.0, neg_t_cri=0.0) -> list:
    '''
    Check if the airfoil is reasonable by rules

    >>> rule_invalid = check_valid(x, yu, yl, RLE=0.0)

    ### Inputs:
    ```text
    x, yu, yl: current airfoil (ndarray)
    RLE:       The leading edge radius of this airfoil
    neg_t_cri:  critical value for checking negative thickness
               e.g., neg_t_cri = -0.01, then only invalid when the thickness is smaller than -0.01
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
    if np.min(thickness) < neg_t_cri:
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

def unify_foil(xu, yu, xl, yl):
    '''
    Transform the airfoil to a unit airfoil

    >>> xu_, yu_, xl_, yl_, twist, chord, tail = unify_foil(xu, yu, xl, yl)

    ### Return:
    ```text
    xu_, yu_, xl_, yl_: unit airfoil (ndarray)
    twist:              twist angle (degree)
    chord:              chord length
    tail:               tail height relative to chord length
    ```
    '''
    if abs(xu[0]-xl[0])>1e-6 or abs(yu[0]-yl[0])>1e-6:
        raise Exception('Two curves do not have the same leading edge')
    
    #* Transform
    xu_ = xu - xu[0]
    xl_ = xl - xl[0]
    yu_ = yu - yu[0]
    yl_ = yl - yl[0]

    #* Twist
    xTE   = 0.5*(xu_[-1]+xl_[-1])
    yTE   = 0.5*(yu_[-1]+yl_[-1])
    twist = np.arctan(yTE/xTE)*180/np.pi
    chord = np.sqrt(xTE**2+yTE**2)

    xu_, yu_, _ = rotate(xu_, yu_, None, angle=-twist, axis='Z')
    xl_, yl_, _ = rotate(xl_, yl_, None, angle=-twist, axis='Z')

    #* Scale
    yu_ = yu_ / xu_[-1]
    yl_ = yl_ / xl_[-1]
    xu_ = xu_ / xu_[-1]
    xl_ = xl_ / xl_[-1]
    
    #* Removing tail
    tail = abs(yu_[-1]) + abs(yl_[-1])

    for ip in range(yu_.shape[0]):
        yu_[ip] -= xu_[ip]*yu_[-1]  

    for ip in range(yl_.shape[0]):
        yl_[ip] -= xl_[ip]*yl_[-1]  

    return xu_, yu_, xl_, yl_, twist, chord, tail


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

    # http://ambrsoft.com/TrigoCalc/Circle3D.htm

    A = p1[0]*(p2[1]-p3[1]) - p1[1]*(p2[0]-p3[0]) + p2[0]*p3[1] - p3[0]*p2[1]
    if np.abs(A) <= 1E-20:
        raise Exception('Finding circle: 3 points in one line')
    
    p1s = p1[0]**2 + p1[1]**2
    p2s = p2[0]**2 + p2[1]**2
    p3s = p3[0]**2 + p3[1]**2

    B = p1s*(p3[1]-p2[1]) + p2s*(p1[1]-p3[1]) + p3s*(p2[1]-p1[1])
    C = p1s*(p2[0]-p3[0]) + p2s*(p3[0]-p1[0]) + p3s*(p1[0]-p2[0])
    D = p1s*(p3[0]*p2[1]-p2[0]*p3[1]) + p2s*(p1[0]*p3[1]-p3[0]*p1[1]) + p3s*(p2[0]*p1[1]-p1[0]*p2[1])

    x0 = -B/2/A
    y0 = -C/2/A
    R  = np.sqrt(B**2+C**2-4*A*D)/2/np.abs(A)

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
    '''

    return R, np.array([x0, y0])

def curve_curvature(x, y):
    '''
    Calculate curvature of points in the curve

    >>> curve = curve_curvature(x, y)

    ### Inputs:
    ```text
    x, y: points of curve (ndarray)
    ```

    Return: curve (ndarray)
    '''
    nn = x.shape[0]
    if nn<3:
        raise Exception('curvature needs at least 3 points')
    
    curve = np.zeros(nn)
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

        curve[i] = curv_

    curve[0] = curve[1]
    curve[-1] = curve[-2]

    return curve


def interplot_sec(sec0: Section, sec1: Section, ratio: float):
    '''
    Interplot a section by ratio. CST coefficients are gained by cst_foil_fit.

    >>> sec = interplot_sec(sec0, sec1, ratio)
    '''
    sec = interplot_basic_sec(sec0, sec1, ratio)

    sec.tail  = (1-ratio)*sec0.tail  + ratio*sec1.tail
    sec.RLE   = (1-ratio)*sec0.RLE   + ratio*sec1.RLE

    sec.cst_u, sec.cst_l = cst_foil_fit(sec.xx, sec.yu, sec.xx, sec.yl, n_cst=sec0.cst_u.shape[0])

    sec.refine_u = None
    sec.refine_l = None

    return sec

#* ===========================================
#* CST foils
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
        
    # Update t0 after adding tail
    if t is None:
        thick = yu-yl
        it = np.argmax(thick)
        t0 = thick[it]

    # Calculate leading edge radius
    x_RLE = 0.005
    yu_RLE = interplot_from_curve(x_RLE, x_, yu)
    yl_RLE = interplot_from_curve(x_RLE, x_, yl)
    R0, _ = find_circle_3p([0.0,0.0], [x_RLE,yu_RLE], [x_RLE,yl_RLE])

    return x_, yu, yl, t0, R0

def naca_to_cst(NACA_series: str, n_cst=7, nn=51):
    '''
    Get CST parameters of a NACA series airfoil

    >>> cst_u, cst_l = naca_to_cst(NACA_series, n_cst, nn)

    ### Inputs:
    ```text
    NACA_series:    4 or 5 digit NACA number string
    n_cst:          number of CST parameters
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
        
    for i in range(nn-2):
        if xu[i+1] < xu[i]:
            xu[i+1] = max(xu[i], 0.5*(xu[i]+xu[i+2]))
        if xl[i+1] < xl[i]:
            xl[i+1] = max(xl[i], 0.5*(xl[i]+xl[i+2]))

    cst_u, cst_l = cst_foil_fit(xu, yu, xl, yl, n_cst=n_cst)

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

def dist_clustcos(nn: int, a0=0.0079, a1=0.96, beta=1.0) -> np.ndarray:
    '''
    Point distribution on x-axis [0, 1]. (More points at both ends)

    >>> xx = dist_clustcos(n, a0, a1, beta)

    ### Inputs:
    ```text
    nn:     total amount of points
    a0:     parameter for distributing points near x=0
    a1:     parameter for distributing points near x=1
    beta:   parameter for distribution points 
    ```
    '''
    aa = np.power((1-np.cos(a0*np.pi))/2.0, beta)
    dd = np.power((1-np.cos(a1*np.pi))/2.0, beta) - aa
    yt = np.linspace(0.0, 1.0, num=nn)
    a  = np.pi*(a0*(1-yt)+a1*yt)
    xx = (np.power((1-np.cos(a))/2.0,beta)-aa)/dd

    return xx

def cst_curve(nn: int, coef: np.array, x=None, xn1=0.5, xn2=1.0):
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
    
    n_cst = coef.shape[0]
    y = np.zeros(nn)
    for ip in range(nn):
        s_psi = 0.0
        for i in range(n_cst):
            xk_i_n = factorial(n_cst-1)/factorial(i)/factorial(n_cst-1-i)
            s_psi += coef[i]*xk_i_n * np.power(x[ip],i) * np.power(1-x[ip],n_cst-1-i)

        C_n1n2 = np.power(x[ip],xn1) * np.power(1-x[ip],xn2)
        y[ip] = C_n1n2*s_psi

    y[0] = 0.0
    y[-1] = 0.0

    return x, y


#* ===========================================
#* Fitting a curve/foil with CST
#* ===========================================

def cst_foil_fit(xu, yu, xl, yl, n_cst=7):
    '''
    Using CST method to fit an airfoil

    This function allows the airfoil has non-zero tail thickness.
    Also allows the airfoil chord length not equals to one.
    #! But yu[0] yl[0] should be 0

    >>> cst_u, cst_l = cst_foil_fit(xu, yu, xl, yl, n_cst=7)

    ### Inputs:
    ```text
    xu, yu:  upper surface points (ndarray)
    xl, yl:  lower surface points (ndarray)
    n_cst:   number of CST parameters
    ```

    ### Return: 
    cst_u, cst_l (ndarray)
    '''
    cst_u = fit_curve(xu, yu, n_cst=n_cst)
    cst_l = fit_curve(xl, yl, n_cst=n_cst)
    return cst_u, cst_l

def fit_curve(x: np.array, y: np.array, n_cst=7, xn1=0.5, xn2=1.0):
    '''
    Using least square method to fit a CST curve
    
    #! Note: y[0] should be 0

    >>> coef = fit_curve(x, y, n_cst, xn1, xn2)

    ### Input:
    ```text
    x, y:    curve points (ndarray)
    n_cst:   number of CST parameters
    ```

    ### Attributes:
    ```text
    Array A: A[nn, n_cst], nn=len(x)
    Array b: b[nn]
    ```

    ### Return: 
    coef (ndarray)
    '''
    nn = x.shape[0]
    L  = x[-1] - x[0]   # type: float
    x_ = (x-x[0])/L     # scaling x to 0~1
    y_ = (y-y[0])/L     # scaling according to L #! This means y[0] should be 0
    b  = y_.copy()

    for ip in range(nn):
        b[ip] -= x_[ip]*y_[-1]  # removing tail

    A = np.zeros((nn, n_cst))
    for ip in range(nn):
        C_n1n2 = np.power(x_[ip],xn1) * np.power(1-x_[ip],xn2)
        for i in range(n_cst):
            xk_i_n = factorial(n_cst-1)/factorial(i)/factorial(n_cst-1-i)
            A[ip][i] = xk_i_n * np.power(x_[ip],i) * np.power(1-x_[ip],n_cst-1-i) * C_n1n2

    solution = lstsq(A, b, rcond=None)

    return solution[0]

def fit_curve_with_twist(x, y, n_cst=7, xn1=0.5, xn2=1.0):
    '''
    Using least square method to fit a CST curve

    >>> coef, chord, twist, thick = fit_curve_with_twist(x, y, n_cst, xn1, xn2)

    ### Input:
    ```text
    x, y:    curve points (ndarray)
    n_cst:   number of CST parameters
    ```

    ### Attributes:
    ```text
    Array A: A[nn, n_cst], nn=len(x)
    Array b: b[nn]
    ```

    ### Return: 
    coef:   CST parameters, ndarray
    chord:  distance between two ends of the curve
    twist:  degree, +z axis
    thick:  maximum relative thickness
    '''
    chord = np.sqrt((x[0]-x[-1])**2+(y[0]-y[-1])**2)
    twist = np.arctan((y[-1]-y[0])/(x[-1]-x[0]))*180/np.pi

    x_ = (x - x[0])/chord
    y_ = (y - y[0])/chord
    x_, y_, _ = rotate(x_, y_, None, angle=-twist, axis='Z')
    thick = np.max(y_, axis=0)

    coef = fit_curve(x_, y_, n_cst=n_cst, xn1=xn1, xn2=xn2)
    
    return coef, chord, twist, thick

def fit_curve_partial(x: np.array, y: np.array, ip0=0, ip1=0,
            n_cst=7, ic0=0, ic1=0, xn1=0.5, xn2=1.0):
    '''
    Using least square method to fit a part of a unit curve

    >>> coef = fit_curve_partial(x: np.array, y: np.array,
    >>>                 ip0=0, ip1=0, n_cst=7, xn1=0.5, xn2=1.0)

    ### Input:
    ```text
    x, y:       curve points (ndarray)
    ip0, ip1:   index of the partial curve x[ip0:ip1] 
    ic0, ic1:   index of the CST parameters cst[ic0:ic1] that are not 0
    n_cst:      number of CST parameters
    ```

    ### Attributes:
    ```text
    Array A: A[nn, n_cst], nn=len(x)
    Array b: b[nn]
    ```

    ### Return: 
    coef (ndarray)
    '''
    ip0 = max(0, ip0)
    if ip1 <= ip0:
        ip1 = x.shape[0]

    ic0 = max(0, ic0)
    if ic1 <= ic0:
        ic1 = n_cst

    #* Fit the partial curve
    A = np.zeros((ip1-ip0, ic1-ic0))
    for ip in range(ip0, ip1):
        C_n1n2 = np.power(x[ip],xn1) * np.power(1-x[ip],xn2)
        for i in range(ic0,ic1):
            xk_i_n = factorial(n_cst-1)/factorial(i)/factorial(n_cst-1-i)
            A[ip-ip0][i-ic0] = xk_i_n * np.power(x[ip],i) * np.power(1-x[ip],n_cst-1-i) * C_n1n2

    solution = lstsq(A, y[ip0:ip1], rcond=None)

    return solution[0]


#* ===========================================
#* Modification of a curve/foil
#* ===========================================

def foil_bump_modify(x: np.array, yu: np.array, yl: np.array,
            xc: float, h: float, s: float, side=1, n_cst=0,
            return_cst=False, keep_tmax=True):
    '''
    Add bumps on the airfoil

    >>> yu_new, yl_new (, cst_u, cst_l) = foil_bump_modify(
    >>>         x: np.array, yu: np.array, yl: np.array, 
    >>>         xc: float, h: float, s: float, side=1,
    >>>         n_cst=0, return_cst=False, keep_tmax=True)

    ### Inputs:
    ```text
    x, yu, yl:  current airfoil (ndarray)
    xc:         x of the bump center
    h:          relative height of the bump (to maximum thickness)
    s:          span of the bump
    side:       +1/-1 upper/lower side of the airfoil
    n_cst:      if specified (>0), then use CST to fit the new foil
    return_cst: if True, also return cst_u, cst_l when n_cst > 0
    keep_tmax:  if True, keep the maximum thickness unchanged
                scale the opposite side of 'side' to keep thickness
    ```

    ### Return:
    yu_new, yl_new (ndarray)
    '''
    yu_new = yu.copy()
    yl_new = yl.copy()
    t0 = np.max(yu_new-yl_new)

    if xc<0.1 or xc>0.9:
        kind = 'H'
    else:
        kind = 'G'

    if side > 0:
        yu_new = add_bump(x, yu_new, xc, h*t0, s, kind=kind)
    else:
        yl_new = add_bump(x, yl_new, xc, h*t0, s, kind=kind)

    if keep_tmax:

        it = np.argmax(yu_new-yl_new)
        tu = np.abs(yu_new[it])
        tl = np.abs(yl_new[it])

        #* Scale the opposite side
        if side > 0:
            rl = (t0-tu)/tl
            yl_new = rl * np.array(yl_new)
        else:
            ru = (t0-tl)/tu
            yu_new = ru * np.array(yu_new)

        t0 = None

    if n_cst > 0:
        # CST reverse
        tail = yu[-1] - yl[-1]
        cst_u, cst_l = cst_foil_fit(x, yu_new, x, yl_new, n_cst=n_cst)
        _, yu_new, yl_new, _, _ = cst_foil(x.shape[0], cst_u, cst_l, x=x, t=t0, tail=tail)
    else:
        cst_u = None
        cst_l = None
    
    if return_cst:
        return yu_new, yl_new, cst_u, cst_l
    else:
        return yu_new, yl_new

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
        yu_i = None

    if coef_upp is not None:
        _, yl_i = cst_curve(nn, coef_low, x=x)
    else:
        yl_i = None

    yu_, yl_ = foil_increment_curve(x, yu, yl, yu_i=yu_i, yl_i=yl_i, t=t)

    return yu_, yl_

def foil_increment_curve(x, yu, yl, yu_i=None, yl_i=None, t=None):
    '''
    Add cst curve by incremental curves

    >>> yu_, yl_ = foil_increment_curve(x, yu, yl, yu_i, yl_i, t=None)

    ### Inputs:
    ```text
    x, yu, yl:  baseline airfoil (ndarray)
    yu_i, yl_i: incremental curves (ndarray)
    t:          relative maximum thickness (optional)
    ```

    ### Return: 
    yu_, yl_ (ndarray)
    '''
    nn = len(x)

    if not isinstance(yu_i, np.ndarray):
        yu_i = np.zeros(nn)

    if not isinstance(yl_i, np.ndarray):
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


#* ===========================================
#* Other functions
#* ===========================================

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
            line = '   %20.9f  %20.9f'%(x[i], yu[i])
            if info:
                line = line + '  %20.9f  %20.9f  %20.9f'%(curv_u[i], thickness[i], camber[i])
            f.write(line+'\n')
            
        f.write('zone T="Low-%d" i= %d \n'%(ID, nn))
        for i in range(nn):
            line = '   %20.9f  %20.9f'%(x[i], yl[i])
            if info:
                line = line + '  %20.9f  %20.9f  %20.9f'%(curv_l[i], thickness[i], camber[i])
            f.write(line+'\n')


