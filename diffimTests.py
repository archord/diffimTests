import numpy as np
from numpy.polynomial.chebyshev import chebval2d
import scipy
import scipy.stats
from scipy.fftpack import fft2, ifft2, fftshift, ifftshift
import scipy.ndimage.filters
import scipy.signal

log_level = None
try:
    import lsst.afw.image as afwImage
    import lsst.afw.math as afwMath
    import lsst.log
    lsst.log.Log.getLogger('afw').setLevel(lsst.log.ERROR)
    lsst.log.Log.getLogger('afw.math').setLevel(lsst.log.ERROR)
    lsst.log.Log.getLogger('afw.image').setLevel(lsst.log.ERROR)
    lsst.log.Log.getLogger('afw.math.convolve').setLevel(lsst.log.ERROR)
    lsst.log.Log.getLogger('TRACE5.afw.math.convolve.convolveWithInterpolation').setLevel(lsst.log.ERROR)
    lsst.log.Log.getLogger('TRACE2.afw.math.convolve.basicConvolve').setLevel(lsst.log.ERROR)
    lsst.log.Log.getLogger('TRACE4.afw.math.convolve.convolveWithBruteForce').setLevel(lsst.log.ERROR)
    import lsst.log.utils as logUtils
    logUtils.traceSetAt('afw', 0)
    log_level = lsst.log.ERROR
except Exception as e:
    print e
    print "LSSTSW has not been set up."

def zscale_image(input_img, contrast=0.25):
    """This emulates ds9's zscale feature. Returns the suggested minimum and
    maximum values to display."""

    samples = input_img.flatten()
    samples = samples[~np.isnan(samples)]
    samples.sort()
    chop_size = int(0.10*len(samples))
    subset = samples[chop_size:-chop_size]

    i_midpoint = int(len(subset)/2)
    I_mid = subset[i_midpoint]

    fit = np.polyfit(np.arange(len(subset)) - i_midpoint, subset, 1)
    # fit = [ slope, intercept]

    z1 = I_mid + fit[0]/contrast * (1-i_midpoint)/1.0
    z2 = I_mid + fit[0]/contrast * (len(subset)-i_midpoint)/1.0
    return z1, z2

def plotImageGrid(images, nrows_ncols=None, extent=None, clim=None, interpolation='none',
                  cmap='gray', imScale=2., cbar=True, titles=None, titlecol=['r','y'], **kwds):
    import matplotlib.pyplot as plt
    import matplotlib
    matplotlib.style.use('ggplot')
    from mpl_toolkits.axes_grid1 import ImageGrid

    def add_inner_title(ax, title, loc, size=None, **kwargs):
        from matplotlib.offsetbox import AnchoredText
        from matplotlib.patheffects import withStroke
        if size is None:
            size = dict(size=plt.rcParams['legend.fontsize'], color=titlecol[0])
        at = AnchoredText(title, loc=loc, prop=size,
                          pad=0., borderpad=0.5,
                          frameon=False, **kwargs)
        ax.add_artist(at)
        at.txt._text.set_path_effects([withStroke(foreground=titlecol[1], linewidth=3)])
        return at

    if nrows_ncols is None:
        tmp = np.int(np.floor(np.sqrt(len(images))))
        nrows_ncols = (tmp, np.int(np.ceil(np.float(len(images))/tmp)))
    if nrows_ncols[0] <= 0:
        nrows_ncols[0] = 1
    if nrows_ncols[1] <= 0:
        nrows_ncols[1] = 1
    size = (nrows_ncols[1]*imScale, nrows_ncols[0]*imScale)
    fig = plt.figure(1, size)
    igrid = ImageGrid(fig, 111,  # similar to subplot(111)
                      nrows_ncols=nrows_ncols, direction='row',  # creates 2x2 grid of axes
                      axes_pad=0.1,  # pad between axes in inch.
                      label_mode="L",  # share_all=True,
                      cbar_location="right", cbar_mode="single", cbar_size='7%')
    extentWasNone = False
    clim_orig = clim
    for i in range(len(images)):
        ii = images[i]
        if hasattr(ii, 'computeImage'):
            img = afwImage.ImageD(ii.getDimensions())
            ii.computeImage(img, doNormalize=False)
            ii = img
        if hasattr(ii, 'getImage'):
            ii = ii.getImage()
        if hasattr(ii, 'getMaskedImage'):
            ii = ii.getMaskedImage().getImage()
        if hasattr(ii, 'getArray'):
            bbox = ii.getBBox()
            if extent is None:
                extentWasNone = True
                extent = (bbox.getBeginX(), bbox.getEndX(), bbox.getBeginY(), bbox.getEndY())
            ii = ii.getArray()
        if extent is not None and not extentWasNone:
            ii = ii[extent[0]:extent[1], extent[2]:extent[3]]
        if clim_orig is None:
            clim = zscale_image(ii)
        if cbar and clim_orig is not None:
            ii = np.clip(ii, clim[0], clim[1])
        im = igrid[i].imshow(ii, origin='lower', interpolation=interpolation, cmap=cmap,
                             extent=extent, clim=clim, **kwds)
        if cbar:
            igrid[i].cax.colorbar(im)
        if titles is not None:  # assume titles is an array or tuple of same length as images.
            t = add_inner_title(igrid[i], titles[i], loc=2)
            t.patch.set_ec("none")
            t.patch.set_alpha(0.5)
        if extentWasNone:
            extent = None
        extentWasNone = False
    return igrid

def gaussian2d(grid, m=None, s=None):
    # see https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.multivariate_normal.html

    if m is None:
        m = [0., 0.]
    if s is None:
        s = [1., 1.]
    cov = [[s[0], 0], [0, s[1]]]
    var = scipy.stats.multivariate_normal(mean=m, cov=cov)
    return var.pdf(grid)

def singleGaussian2d(x, y, xc, yc, sigma_x=1., sigma_y=1., theta=0., offset=0.):
    theta = (theta/180.) * np.pi
    cos_theta2, sin_theta2 = np.cos(theta)**2., np.sin(theta)**2.
    sigma_x2, sigma_y2 = sigma_x**2., sigma_y**2.
    a = cos_theta2/(2.*sigma_x2) + sin_theta2/(2.*sigma_y2)
    b = -(np.sin(2.*theta))/(4.*sigma_x2) + (np.sin(2.*theta))/(4.*sigma_y2)
    c = sin_theta2/(2.*sigma_x2) + cos_theta2/(2.*sigma_y2)
    xxc, yyc = x-xc, y-yc
    out = np.exp(-(a*(xxc**2.) + 2.*b*xxc*yyc + c*(yyc**2.)))
    if offset != 0.:
        out += offset
    out /= out.sum()
    return out

# Make the two "images". im1 is the template, im2 is the science
# image.
# NOTE: having sources near the edges really messes up the
# fitting (probably because of the convolution). So make sure no
# sources are near the edge.
# NOTE: also it seems that having the variable source with a large
# flux increase also messes up the fitting (seems to lead to
# overfitting -- perhaps to the source itself). This might be fixed by
# adding more constant sources.
# varFlux1 is the flux of variable sources in im1 (template). If zero, then the variable sources are
#  "new" sources in im2.
# varFlux2 is the flux of variable sources in im2 (science img)

def makeFakeImages(imSize=None, sky=2000., psf1=None, psf2=None, offset=None,
                   scintillation=0., psf_yvary_factor=0.2,
                   theta1=0., theta2=-45., varFlux1=0, varFlux2=1500,
                   variablesNearCenter=True,
                   im2background=10., n_sources=500, sourceFluxRange=None, psfSize=None,
                   seed=66, fast=True, verbose=False):
    if seed is not None:  # use None if you set the seed outside of this func.
        np.random.seed(seed)

    # psf1 = 1.6 # sigma in pixels im1 will be template
    # psf2 = 2.2 # sigma in pixels im2 will be science image. make the psf in this image slighly offset and elongated
    psf1 = [1.6, 1.6] if psf1 is None else psf1
    psf2 = [1.8, 2.2] if psf2 is None else psf2
    # offset = 0.2  # astrometric offset (pixels) between the two images
    offset = [0.2, 0.2] if offset is None else offset
    sourceFluxRange = (50, 30000) if sourceFluxRange is None else sourceFluxRange
    if verbose:
        print 'Template PSF:', psf1, theta1
        print 'Science PSF:', psf2, theta2
        print np.sqrt(psf2[0]**2 - psf1[1]**2)
        print 'Offset:', offset

    imSize = (512, 512) if imSize is None else imSize
    xim = np.arange(-imSize[0]//2, imSize[0]//2, 1)
    yim = np.arange(-imSize[1]//2, imSize[1]//2, 1)
    x0im, y0im = np.meshgrid(xim, yim)
    fluxes = np.random.uniform(sourceFluxRange[0], sourceFluxRange[1], n_sources)
    xposns = np.random.uniform(xim.min()+40, xim.max()-40, n_sources)
    yposns = np.random.uniform(yim.min()+40, yim.max()-40, n_sources)
    fluxSortedInds = np.argsort(xposns**2. + yposns**2.)

    if not hasattr(varFlux1, "__len__"):
        varFlux1 = [varFlux1]
    if not hasattr(varFlux2, "__len__"):
        varFlux2 = [varFlux2]
    if len(varFlux1) == 1:
        varFlux1 = np.repeat(varFlux1[0], len(varFlux2))
    if variablesNearCenter:
        # Make the sources closest to the center of the image the ones that increases in flux
        inds = fluxSortedInds[:len(varFlux2)]
    else:  # Just choose random ones
        inds = np.arange(len(varFlux2))
    #print inds, xposns[inds], yposns[inds]

    ## Need to add poisson noise of stars as well...
    im1 = np.random.poisson(sky, size=x0im.shape).astype(float)  # sigma of template
    im2 = np.random.poisson(sky, size=x0im.shape).astype(float)  # sigma of science image

    # variation in y-width of psf in science image across (x-dim of) image
    psf2_yvary = psf_yvary_factor * (yim.mean() - yposns) / yim.max()
    if verbose:
        print 'PSF y spatial-variation:', psf2_yvary.min(), psf2_yvary.max()
    # psf2_yvary[:] = 1.1  # turn it off for now, just add a constant 1.1 pixel horizontal width

    scintillationNoiseX = scintillationNoiseY = np.zeros(len(fluxes))
    if scintillation > 0.:
        scintillationNoiseX = np.random.normal(0., scintillation, len(fluxes))
        scintillationNoiseY = np.random.normal(0., scintillation, len(fluxes))

    starSize = 32  # make stars using "psf's" of this size (instead of whole image)
    varSourceInd = 0
    fluxes2 = fluxes.copy()
    for i in fluxSortedInds:
        if i in inds:
            flux = varFlux1[varSourceInd]
        else:
            flux = fluxes[i]
        fluxes[i] = flux
        if fast:
            offset1 = [yposns[i]-np.floor(yposns[i]),
                       xposns[i]-np.floor(xposns[i])]
            tmp1 = makePsf(starSize, psf1, theta1, offset=offset1)
            tmp1 *= flux
            offset2 = [xposns[i]+imSize[0]//2, yposns[i]+imSize[1]//2]
            im1[(offset2[1]-starSize+1):(offset2[1]+starSize),
                (offset2[0]-starSize+1):(offset2[0]+starSize)] += tmp1
        else:
            tmp1 = singleGaussian2d(x0im, y0im, xposns[i], yposns[i], psf1[0], psf1[1], theta=theta1)
            tmp1 *= flux
            im1 += tmp1

        if i in inds:
            vf2 = varFlux2[varSourceInd]
            if vf2 < 1:  # option to input it as fractional flux change
                vf2 = flux * vf2
            changedCentroid = (xposns[i]+imSize[0]//2, yposns[i]+imSize[1]//2)
            if verbose:
                print 'Variable source:', i, changedCentroid[0], changedCentroid[1], flux, flux + vf2
            flux += vf2
            fluxes2[i] = flux
            varSourceInd += 1
        xposn = xposns[i] + offset[0] + scintillationNoiseX[i]
        yposn = yposns[i] + offset[0] + scintillationNoiseY[i]

        if fast:
            offset1 = [yposn-np.floor(yposn), xposn-np.floor(xposn)]
            tmp = makePsf(starSize, [psf2[0], psf2[1] + psf2_yvary[i]], theta2, offset=offset1)
            tmp *= flux
            offset2 = [xposn+imSize[0]//2, yposn+imSize[1]//2]
            im2[(offset2[1]-starSize+1):(offset2[1]+starSize),
                (offset2[0]-starSize+1):(offset2[0]+starSize)] += tmp
        else:
            tmp = singleGaussian2d(x0im, y0im, xposn, yposn,
                                   psf2[0], psf2[1] + psf2_yvary[i], theta=theta2)
            tmp *= flux
            im2 += tmp

    var_im1 = im1.copy()
    var_im2 = im2.copy()
    im1 -= sky
    im2 -= sky

    # Add a (constant, for now) background offset to im2
    if im2background != 0.:  # im2background = 10.
        print 'Background:', im2background
        im2 += im2background

    if psfSize is None:
        psfSize = imSize

    im1_psf = makePsf(psfSize, psf1, theta1)
    #im2_psf = makePsf(psfSize, psf2, theta2, offset)
    # Don't include any astrometric "error" in the PSF, see how well the diffim algo. handles it.
    im2_psf = makePsf(psfSize, psf2, theta2)
    centroids = np.column_stack((xposns + imSize[0]//2, yposns + imSize[1]//2, fluxes, fluxes2))
    return im1, im2, im1_psf, im2_psf, var_im1, var_im2, centroids, inds

def makePsf(psfSize, sigma, theta, offset=[0, 0]):
    x = np.arange(-psfSize+1, psfSize, 1)
    y = x.copy()
    y0, x0 = np.meshgrid(x, y)
    psf = singleGaussian2d(x0, y0, offset[0], offset[1], sigma[0], sigma[1], theta=theta)
    return psf

# Okay, here we start the A&L basis functions...
# Update: it looks like the actual code in the stack uses chebyshev1 polynomials!
# Note these are essentially the same but with different scale factors.

# Here beta is a rescale factor but this is NOT what it is really used for.
# Can be used to rescale so that sigGauss[1] = sqrt(sigmaPsf_I^2 - sigmaPsf_T^2)
def chebGauss2d(x, y, m=None, s=None, ord=[0,0], beta=1., verbose=False):
    if m is None:
        m = [0., 0.]
    if s is None:
        s = [1., 1.]
    # cov = [[s[0], 0], [0, s[1]]]
    coefLen = np.max(ord)+1
    coef0 = np.zeros(coefLen)
    coef0[ord[0]] = 1
    coef1 = np.zeros(coefLen)
    coef1[ord[1]] = 1
    if verbose:
        print s, beta, ord, coef0, coef1
    ga = singleGaussian2d(x, y, 0, 0, s[0]/beta, s[1]/beta)
    ch = chebval2d(x, y, c=np.outer(coef0, coef1))
    return ch * ga

# use same parameters as from the stack.
# TBD: is a degGauss of 2 mean it goes up to order 2 (i.e. $x^2$)? Or
# is it 2 orders so it only goes up to linear ($x$)? Probably the
# former, so that's what we'll use.

# Parameters from stack
# betaGauss is actually the scale factor for sigGauss -> sigGauss[0] = sigGauss[1]/betaGauss and
#   sigGauss[2] = sigGauss[1] * betaGauss. Looks like here, betaGauss is 2 (see sigGauss below) but
#   we'll just set it to 1.
# Note should rescale sigGauss so sigGauss[1] = sqrt(sigma_I^2 - sigma_T^2)
# betaGauss = 1   # in the Becker et al. paper betaGauss is 1 but PSF is more like 2 pixels?
# sigGauss = [0.75, 1.5, 3.0]
# degGauss = [4, 2, 2]
# # Parameters from and Becker et al. (2012)
# degGauss = [6, 4, 2]

def getALChebGaussBases(x0, y0, sigGauss=None, degGauss=None, betaGauss=1, verbose=True):
    sigGauss = [0.75, 1.5, 3.0] if sigGauss is None else sigGauss
    #degGauss = [4, 2, 2] if degGauss is None else degGauss
    degGauss = [6, 4, 2] if degGauss is None else degGauss

    # Old, too many bases:
    #basis = [chebGauss2d(x0, y0, grid, m=[0,0], s=[sig0,sig1], ord=[deg0,deg1], beta=betaGauss, verbose=False) for i0,sig0 in enumerate(sigGauss) for i1,sig1 in enumerate(sigGauss) for deg0 in range(degGauss[i0]) for deg1 in range(degGauss[i1])]

    def get_valid_inds(Nmax):
        tmp = np.add.outer(range(Nmax+1), range(Nmax+1))
        return np.where(tmp <= Nmax)

    inds = [get_valid_inds(i) for i in degGauss]
    if verbose:
        for i in inds:
            print i
    basis = [chebGauss2d(x0, y0, m=[0,0], s=[sig,sig], ord=[inds[i][0][ind], inds[i][1][ind]],
                         beta=betaGauss, verbose=verbose) for i,sig in enumerate(sigGauss) for
             ind in range(len(inds[i][0]))]
    return basis

# Convolve im1 (template) with the basis functions, and make these the *new* bases.
# Input 'basis' is the output of getALChebGaussBases().

def makeImageBases(im1, basis):
    #basis2 = [scipy.signal.fftconvolve(im1, b, mode='same') for b in basis]
    basis2 = [scipy.ndimage.filters.convolve(im1, b, mode='constant') for b in basis]
    return basis2

def makeSpatialBases(im1, basis, basis2, spatialKernelOrder=2, spatialBackgroundOrder=2, verbose=False):
    # Then make the spatially modified basis by simply multiplying the constant
    # basis (basis2 from makeImageBases()) by a polynomial along the image coordinate.
    # Note that since we *are* including i=0, this new basis *does include* basis2 and
    # thus can replace it.

    # Here beta is a rescale factor but this is NOT what it is really used for.
    # Can be used to rescale so that sigGauss[1] = sqrt(sigmaPsf_I^2 - sigmaPsf_T^2)

    # Apparently the stack uses a spatial kernel order of 2? (2nd-order?)
    #spatialKernelOrder = 2  # 0
    # Same for background order.
    #spatialBackgroundOrder = 2

    def cheb2d(x, y, ord=[0,0], verbose=False):
        coefLen = np.max(ord)+1
        coef0 = np.zeros(coefLen)
        coef0[ord[0]] = 1
        coef1 = np.zeros(coefLen)
        coef1[ord[1]] = 1
        if verbose:
            print ord, coef0, coef1
        ch = chebval2d(x, y, c=np.outer(coef0, coef1))
        return ch

    def get_valid_inds(Nmax):
        tmp = np.add.outer(range(Nmax+1), range(Nmax+1))
        return np.where(tmp <= Nmax)

    spatialBasis = bgBasis = None

    spatialInds = get_valid_inds(spatialKernelOrder)
    if verbose:
        print spatialInds

    #xim = np.arange(np.int(-np.floor(im1.shape[0]/2.)), np.int(np.floor(im1.shape[0]/2)))
    #yim = np.arange(np.int(-np.floor(im1.shape[1]/2.)), np.int(np.floor(im1.shape[1]/2)))
    x0im, y0im = getImageGrid(im1) #np.meshgrid(xim, yim)

    # Note the ordering of the loop is important! Make the basis2 the last one so the first set of values
    # that are returned are all of the original (basis2) unmodified bases.
    # Store "spatialBasis" which is the kernel basis and the spatial basis separated so we can recompute the
    # final kernel at the end. Include in index 2 the "original" kernel basis as well.
    if spatialKernelOrder > 0:
        spatialBasis = [[basis2[bi], cheb2d(x0im, y0im, ord=[spatialInds[0][i], spatialInds[1][i]], verbose=False),
                         basis[bi]] for i in range(1,len(spatialInds[0])) for bi in range(len(basis2))]
        # basis2m = [b * cheb2d(x0im, y0im, ord=[spatialInds[0][i], spatialInds[1][i]], verbose=False) for
        # i in range(1,len(spatialInds[0])) for b in basis2]

    spatialBgInds = get_valid_inds(spatialBackgroundOrder)
    if verbose:
        print spatialBgInds

    # Then make the spatial background part
    if spatialBackgroundOrder > 0:
        bgBasis = [cheb2d(x0im, y0im, ord=[spatialBgInds[0][i], spatialBgInds[1][i]], verbose=False) for
                   i in range(len(spatialBgInds[0]))]

    return spatialBasis, bgBasis

# Collect the bases into a single matrix
# ITMT, let's make sure all the bases are on a reasonable scale.
def collectAllBases(basis2, spatialBasis, bgBasis, verbose=False):

    basis2a = np.vstack([b.flatten() for b in basis2]).T

    constKernelIndices = np.arange(0, basis2a.shape[1])
    if verbose:
        print constKernelIndices

    nonConstKernelIndices = None
    if spatialBasis is not None:
        b1 = np.vstack([(b[0]*b[1]).flatten() for b in spatialBasis]).T
        nonConstKernelIndices = np.arange(basis2a.shape[1], basis2a.shape[1]+b1.shape[1])
        basis2a = np.hstack([basis2a, b1])
        if verbose:
            print nonConstKernelIndices

    bgIndices = None
    if bgBasis is not None:
        b1 = np.vstack([b.flatten() for b in bgBasis]).T
        bgIndices = np.arange(basis2a.shape[1], basis2a.shape[1]+b1.shape[1])
        basis2a = np.hstack([basis2a, b1])
        if verbose:
            print bgIndices

    # Rescale the bases so that the "standard" A&L linear fit will work (i.e. when squared, not too large!)
    basisOffset = 0.  # basis2a.mean(0) + 0.1
    basisScale = basis2a.std(0) + 0.1    # avoid division by zero
    basis2a = (basis2a-basisOffset)/(basisScale)
    return basis2a, (constKernelIndices, nonConstKernelIndices, bgIndices), (basisOffset, basisScale)

# Do the linear fit to compute the matching kernel. This is NOT the
# same fit as is done by standard A&L but gives the same results. This
# will not work for very large images. See below. The resulting fit is
# the matched template.

def doTheLinearFitOLD(basis2a, im2, verbose=False):
    pars, resid, _, _ = np.linalg.lstsq(basis2a, im2.flatten())
    fit = (pars * basis2a).sum(1).reshape(im2.shape)
    if verbose:
        print resid, np.sum((im2 - fit.reshape(im2.shape))**2)
    return pars, fit, resid

# Create the $b_i$ and $M_{ij}$ from the A&L (1998) and Becker (2012)
# papers. This was done wrong in the previous version of notebook 3
# (and above), although it gives identical results.

def doTheLinearFitAL(basis2a, im2, verbose=False):
    b = (basis2a.T * im2.flatten()).sum(1)
    M = np.dot(basis2a.T, basis2a)
    pars, resid, _, _ = np.linalg.lstsq(M, b)
    fit = (pars * basis2a).sum(1).reshape(im2.shape)
    if verbose:
        print resid, np.sum((im2 - fit.reshape(im2.shape))**2)
    return pars, fit, resid

# Also generate the matching kernel from the resulting pars.

# Look at the resulting matching kernel by multiplying the fitted
# parameters times the original basis funcs. and test that actually
# convolving it with the template gives us a good subtraction.

# Here, we'll just compute the spatial part at x,y=0,0
# (i.e. x,y=256,256 in img coords)

def getMatchingKernelAL(pars, basis, constKernelIndices, nonConstKernelIndices, spatialBasis,
                        basisScale, basisOffset=0, xcen=256, ycen=256, verbose=False):
    kbasis1 = np.vstack([b.flatten() for b in basis]).T
    kbasis1 = (kbasis1 - basisOffset) / basisScale[constKernelIndices]
    kfit1 = (pars[constKernelIndices] * kbasis1).sum(1).reshape(basis[0].shape)

    kbasis2 = np.vstack([(b[2]*b[1][xcen, ycen]).flatten() for b in spatialBasis]).T
    kbasis2 = (kbasis2 - basisOffset) / basisScale[nonConstKernelIndices]
    kfit2 = (pars[nonConstKernelIndices] * kbasis2).sum(1).reshape(basis[0].shape)

    kfit = kfit1 + kfit2
    if verbose:
        print kfit1.sum(), kfit2.sum(), kfit.sum()
    # this is necessary if the source changes a lot - prevent the kernel from incorporating that change in flux
    kfit /= kfit.sum()
    return kfit


# Compute the "ALZC" post-conv. kernel from kfit

# Note unlike previous notebooks, here because the PSF is varying,
# we'll just use `fit2` rather than `im2-conv_im1` as the diffim,
# since `fit2` already incorporates the spatially varying PSF.
# sig1 and sig2 are the same as those input to makeFakeImages().

# def computeCorrectionKernelALZC(kappa, sig1=0.2, sig2=0.2):
#     def kernel_ft2(kernel):
#         FFT = fft2(kernel)
#         return FFT
#     def post_conv_kernel_ft2(kernel, sig1=1., sig2=1.):
#         kft = kernel_ft2(kernel)
#         return np.sqrt((sig1**2 + sig2**2) / (sig1**2 + sig2**2 * kft**2))
#     def post_conv_kernel2(kernel, sig1=1., sig2=1.):
#         kft = post_conv_kernel_ft2(kernel, sig1, sig2)
#         out = ifft2(kft)
#         return out

#     pck = post_conv_kernel2(kappa, sig1=sig2, sig2=sig1)
#     pck = np.fft.ifftshift(pck.real)
#     #print np.unravel_index(np.argmax(pck), pck.shape)

#     # I think we actually need to "reverse" the PSF, as in the ZOGY (and Kaiser) papers... let's try it.
#     # This is the same as taking the complex conjugate in Fourier space before FFT-ing back to real space.
#     if False:
#         # I still think we need to flip it in one axis (TBD: figure this out!)
#         pck = pck[::-1, :]

#     return pck


# Compute the (corrected) diffim's new PSF
# post_conv_psf = phi_1(k) * sym.sqrt((sig1**2 + sig2**2) / (sig1**2 + sig2**2 * kappa_ft(k)**2))
# we'll parameterize phi_1(k) as a gaussian with sigma "psfsig1".
# im2_psf is the the psf of im2

# def computeCorrectedDiffimPsfALZC(kappa, im2_psf, sig1=0.2, sig2=0.2):
#     def post_conv_psf_ft2(psf, kernel, sig1=1., sig2=1.):
#         # Pad psf or kernel symmetrically to make them the same size!
#         if psf.shape[0] < kernel.shape[0]:
#             while psf.shape[0] < kernel.shape[0]:
#                 psf = np.pad(psf, (1, 1), mode='constant')
#         elif psf.shape[0] > kernel.shape[0]:
#             while psf.shape[0] > kernel.shape[0]:
#                 kernel = np.pad(kernel, (1, 1), mode='constant')
#         psf_ft = fft2(psf)
#         kft = fft2(kernel)
#         out = psf_ft * np.sqrt((sig1**2 + sig2**2) / (sig1**2 + sig2**2 * kft**2))
#         return out
#     def post_conv_psf(psf, kernel, sig1=1., sig2=1.):
#         kft = post_conv_psf_ft2(psf, kernel, sig1, sig2)
#         out = ifft2(kft)
#         return out

#     im2_psf_small = im2_psf
#     # First compute the science image's (im2's) psf, subset on -16:15 coords
#     if im2_psf.shape[0] > 50:
#         x0im, y0im = getImageGrid(im2_psf)
#         x = np.arange(-16, 16, 1)
#         y = x.copy()
#         x0, y0 = np.meshgrid(x, y)
#         im2_psf_small = im2_psf[(x0im.max()+x.min()+1):(x0im.max()-x.min()+1),
#                                 (y0im.max()+y.min()+1):(y0im.max()-y.min()+1)]
#     pcf = post_conv_psf(psf=im2_psf_small, kernel=kappa, sig1=sig2, sig2=sig1)
#     pcf = pcf.real / pcf.real.sum()
#     return pcf

def computeClippedImageStats(im, low=3, high=3, ignore=None):
    im = im[~(np.isnan(im) | np.isinf(im))]
    if ignore is not None:
        for i in ignore:
            im = im[im != i]
    tmp = im
    if low != 0 and high != 0 and tmp.min() != tmp.max():
        _, low, upp = scipy.stats.sigmaclip(tmp, low=low, high=high)
        if not np.isnan(low) and not np.isnan(upp) and low != upp:
            tmp = im[(im > low) & (im < upp)]
    mean1 = np.nanmean(tmp)
    sig1 = np.nanstd(tmp)
    return mean1, sig1, np.nanmin(im), np.nanmax(im)


# compute rms x- and y- pixel offset between two catalogs. Assume input is 2- or 3-column dataframe.
# Assume 1st column is x-coord and 2nd is y-coord. 
# If 3-column then 3rd column is flux and use flux as weighting on shift calculation (not implemented yet)
def computeOffset(src1, src2, threshold=0.5):
    dist = np.sqrt(np.add.outer(src1.iloc[:, 0], -src2.iloc[:, 0])**2. +
                   np.add.outer(src1.iloc[:, 1], -src2.iloc[:, 1])**2.)  # in pixels
    matches = np.where(dist <= threshold)
    match1 = src1.iloc[matches[0], :]
    match2 = src2.iloc[matches[1], :]
    if len(matches[0]) > src1.shape[0]:
        print 'WARNING: Threshold for ast. matching is probably too small:', match1.shape[0], src1.shape[0]
    if len(matches[1]) > src2.shape[0]:
        print 'WARNING: Threshold for ast. matching is probably too small:', match2.shape[0], src2.shape[0]
    dx = (match1.iloc[:, 0].values - match2.iloc[:, 0].values)**2.
    dy = (match1.iloc[:, 1].values - match2.iloc[:, 1].values)**2.
    rms = dx + dy
    rms2, low, upp = scipy.stats.sigmaclip(rms, low=5, high=5)
    dx = dx[(rms >= low) & (rms <= upp)].mean()  # Note this returns the variance (astrometric noise squared)
    dy = dy[(rms >= low) & (rms <= upp)].mean()
    rms = np.sqrt(rms2.mean())
    return dx, dy, rms


def getImageGrid(im):
    xim = np.arange(np.int(-np.floor(im.shape[0]/2.)), np.int(np.floor(im.shape[0]/2)))
    yim = np.arange(np.int(-np.floor(im.shape[1]/2.)), np.int(np.floor(im.shape[1]/2)))
    x0im, y0im = np.meshgrid(xim, yim)
    return x0im, y0im


# Here, im2 is science, im1 is template
def performAlardLupton(im1, im2, sigGauss=None, degGauss=None, betaGauss=1, kernelSize=25,
                       spatialKernelOrder=2, spatialBackgroundOrder=2, doALZCcorrection=True,
                       preConvKernel=None, sig1=None, sig2=None, im2Psf=None, verbose=False):
    x = np.arange(-kernelSize+1, kernelSize, 1)
    y = x.copy()
    x0, y0 = np.meshgrid(x, y)

    im2_orig = im2
    if preConvKernel is not None:
        im2 = scipy.ndimage.filters.convolve(im2, preConvKernel, mode='constant')

    basis = getALChebGaussBases(x0, y0, sigGauss=sigGauss, degGauss=degGauss,
                                betaGauss=betaGauss, verbose=verbose)
    basis2 = makeImageBases(im1, basis)
    spatialBasis, bgBasis = makeSpatialBases(im1, basis, basis2, verbose=verbose)
    basis2a, (constKernelIndices, nonConstKernelIndices, bgIndices), (basisOffset, basisScale) \
        = collectAllBases(basis2, spatialBasis, bgBasis)
    del bgBasis
    del basis2

    pars, fit, resid = doTheLinearFitAL(basis2a, im2)
    del basis2a
    xcen = np.int(np.floor(im1.shape[0]/2.))
    ycen = np.int(np.floor(im1.shape[1]/2.))

    kfit = getMatchingKernelAL(pars, basis, constKernelIndices, nonConstKernelIndices,
                               spatialBasis, basisScale, basisOffset, xcen=xcen, ycen=ycen,
                               verbose=verbose)
    del basis
    del spatialBasis
    diffim = im2 - fit
    psf = im2Psf
    if doALZCcorrection:
        if sig1 is None:
            _, sig1, _, _ = computeClippedImageStats(im1)
        if sig2 is None:
            _, sig2, _, _ = computeClippedImageStats(im2)

        pck = computeDecorrelationKernel(kfit, sig1**2, sig2**2, preConvKernel=preConvKernel)
        pci = scipy.ndimage.filters.convolve(diffim, pck, mode='constant')
        if im2Psf is not None:
            psf = computeCorrectedDiffimPsf(kfit, im2Psf, svar=sig1**2, tvar=sig2**2)
        diffim = pci

    return diffim, psf, kfit

# Compute the ZOGY eqn. (13):
# $$
# \widehat{D} = \frac{F_r\widehat{P_r}\widehat{N} -
# F_n\widehat{P_n}\widehat{R}}{\sqrt{\sigma_n^2 F_r^2
# |\widehat{P_r}|^2 + \sigma_r^2 F_n^2 |\widehat{P_n}|^2}}
# $$
# where $D$ is the optimal difference image, $R$ and $N$ are the
# reference and "new" image, respectively, $P_r$ and $P_n$ are their
# PSFs, $F_r$ and $F_n$ are their flux-based zero-points (which we
# will set to one here), $\sigma_r^2$ and $\sigma_n^2$ are their
# variance, and $\widehat{D}$ denotes the FT of $D$.

# In all functions, im1 is R (reference, or template) and im2 is N (new, or science)
def ZOGYUtils(im1, im2, im1_psf, im2_psf, sig1=None, sig2=None, F_r=1., F_n=1.):
    if sig1 is None and im1 is not None:
        _, sig1, _, _ = computeClippedImageStats(im1)
    if sig2 is None and im2 is not None:
        _, sig2, _, _ = computeClippedImageStats(im2)

    P_r = im1_psf
    P_n = im2_psf
    sigR = sig1
    sigN = sig2
    P_r_hat = fft2(P_r)
    P_n_hat = fft2(P_n)
    denom = np.sqrt((sigN**2 * F_r**2 * np.abs(P_r_hat)**2) + (sigR**2 * F_n**2 * np.abs(P_n_hat)**2))

    return sigR, sigN, P_r_hat, P_n_hat, denom


# In all functions, im1 is R (reference, or template) and im2 is N (new, or science)
def performZOGY(im1, im2, im1_psf, im2_psf, sig1=None, sig2=None, F_r=1., F_n=1.):
    sigR, sigN, P_r_hat, P_n_hat, denom = ZOGYUtils(im1, im2, im1_psf, im2_psf, sig1, sig2, F_r, F_n)

    R_hat = fft2(im1)
    N_hat = fft2(im2)
    numerator = (F_r * P_r_hat * N_hat - F_n * P_n_hat * R_hat)
    d_hat = numerator / denom

    d = ifft2(d_hat)
    D = ifftshift(d.real)

    return D


# In all functions, im1 is R (reference, or template) and im2 is N (new, or science)
def performZOGYImageSpace(im1, im2, im1_psf, im2_psf, sig1=None, sig2=None, F_r=1., F_n=1.):
    sigR, sigN, P_r_hat, P_n_hat, denom = ZOGYUtils(im1, im2, im1_psf, im2_psf, sig1, sig2, F_r, F_n)
    K_r_hat = P_r_hat / denom
    K_n_hat = P_n_hat / denom
    K_r = np.fft.ifft2(K_r_hat).real
    K_n = np.fft.ifft2(K_n_hat).real

    # Note these are reverse-labelled, this is CORRECT!
    im1c = scipy.signal.convolve2d(im1, K_n.real, mode='same', boundary='fill', fillvalue=0.)
    im2c = scipy.signal.convolve2d(im2, K_r.real, mode='same', boundary='fill', fillvalue=0.)
    D = im2c - im1c

    return D


## Also compute the diffim's PSF (eq. 14)
def computeZOGYDiffimPsf(im1, im2, im1_psf, im2_psf, sig1=None, sig2=None, F_r=1., F_n=1.):
    sigR, sigN, P_r_hat, P_n_hat, denom = ZOGYUtils(im1, im2, im1_psf, im2_psf, sig1, sig2, F_r, F_n)

    F_D_numerator = F_r * F_n
    F_D_denom = np.sqrt(sigN**2 * F_r**2 + sigR**2 * F_n**2)
    F_D = F_D_numerator / F_D_denom

    P_d_hat_numerator = (F_r * F_n * P_r_hat * P_n_hat)
    P_d_hat = P_d_hat_numerator / (F_D * denom)

    P_d = np.fft.ifft2(P_d_hat)
    P_D = np.fft.ifftshift(P_d).real

    return P_D, F_D


# Compute the corrected ZOGY "S_corr" (eq. 25)
# Currently only implemented is V(S_N) and V(S_R)
# Want to implement astrometric variance Vast(S_N) and Vast(S_R)
def performZOGY_Scorr(im1, im2, var_im1, var_im2, im1_psf, im2_psf,
                      sig1=None, sig2=None, F_r=1., F_n=1., xVarAst=0., yVarAst=0., D=None):
    sigR, sigN, P_r_hat, P_n_hat, denom = ZOGYUtils(im1, im2, im1_psf, im2_psf, sig1, sig2, F_r, F_n)
    if D is None:
        D = performZOGYImageSpace(im1, im2, im1_psf, im2_psf, sigR, sigN, F_r, F_n)
    P_D, F_D = computeZOGYDiffimPsf(im1, im2, im1_psf, im2_psf, sigR, sigN, F_r, F_n)
    # P_r_hat = np.fft.fftshift(P_r_hat)  # Not sure why I need to do this but it seems that I do.
    # P_n_hat = np.fft.fftshift(P_n_hat)

    # Adjust the variance planes of the two images to contribute to the final detection
    # (eq's 26-29).
    k_r_hat = F_r * F_n**2 * np.conj(P_r_hat) * np.abs(P_n_hat)**2 / denom**2.
    k_n_hat = F_n * F_r**2 * np.conj(P_n_hat) * np.abs(P_r_hat)**2 / denom**2.

    k_r = np.fft.ifft2(k_r_hat)
    k_r = k_r.real  # np.abs(k_r).real #np.fft.ifftshift(k_r).real
    k_r = np.roll(np.roll(k_r, -1, 0), -1, 1)
    k_n = np.fft.ifft2(k_n_hat)
    k_n = k_n.real  # np.abs(k_n).real #np.fft.ifftshift(k_n).real
    k_n = np.roll(np.roll(k_n, -1, 0), -1, 1)
    var1c = scipy.ndimage.filters.convolve(var_im1, k_r**2., mode='constant')
    var2c = scipy.ndimage.filters.convolve(var_im2, k_n**2., mode='constant')

    fGradR = fGradN = 0.
    if xVarAst + yVarAst > 0:  # Do the astrometric variance correction
        S_R = scipy.ndimage.filters.convolve(im1, k_r, mode='constant')
        gradRx, gradRy = np.gradient(S_R)
        fGradR = xVarAst * gradRx**2. + yVarAst * gradRy**2.
        S_N = scipy.ndimage.filters.convolve(im2, k_n, mode='constant')
        gradNx, gradNy = np.gradient(S_N)
        fGradN = xVarAst * gradNx**2. + yVarAst * gradNy**2.

    PD_bar = np.fliplr(np.flipud(P_D))
    S = scipy.ndimage.filters.convolve(D, PD_bar, mode='constant') * F_D
    S_corr = S / np.sqrt(var1c + var2c + fGradR + fGradN)
    return S_corr, S, D, P_D, F_D, var1c, var2c


def computePixelCovariance(diffim, diffim2=None):
    diffim = diffim/diffim.std()
    shifted_imgs2 = None
    shifted_imgs = [
        diffim,
        np.roll(diffim, 1, 0), np.roll(diffim, -1, 0), np.roll(diffim, 1, 1), np.roll(diffim, -1, 1),
        np.roll(np.roll(diffim, 1, 0), 1, 1), np.roll(np.roll(diffim, 1, 0), -1, 1),
        np.roll(np.roll(diffim, -1, 0), 1, 1), np.roll(np.roll(diffim, -1, 0), -1, 1),
        np.roll(diffim, 2, 0), np.roll(diffim, -2, 0), np.roll(diffim, 2, 1), np.roll(diffim, -2, 1),
        np.roll(diffim, 3, 0), np.roll(diffim, -3, 0), np.roll(diffim, 3, 1), np.roll(diffim, -3, 1),
        np.roll(diffim, 4, 0), np.roll(diffim, -4, 0), np.roll(diffim, 4, 1), np.roll(diffim, -4, 1),
        np.roll(diffim, 5, 0), np.roll(diffim, -5, 0), np.roll(diffim, 5, 1), np.roll(diffim, -5, 1),
    ]
    shifted_imgs = np.vstack([i.flatten() for i in shifted_imgs])
    #out = np.corrcoef(shifted_imgs)
    if diffim2 is not None:
        shifted_imgs2 = [
            diffim2,
            np.roll(diffim2, 1, 0), np.roll(diffim2, -1, 0), np.roll(diffim2, 1, 1), np.roll(diffim2, -1, 1),
            np.roll(np.roll(diffim2, 1, 0), 1, 1), np.roll(np.roll(diffim2, 1, 0), -1, 1),
            np.roll(np.roll(diffim2, -1, 0), 1, 1), np.roll(np.roll(diffim2, -1, 0), -1, 1),
            np.roll(diffim2, 2, 0), np.roll(diffim2, -2, 0), np.roll(diffim2, 2, 1), np.roll(diffim2, -2, 1),
            np.roll(diffim2, 3, 0), np.roll(diffim2, -3, 0), np.roll(diffim2, 3, 1), np.roll(diffim2, -3, 1),
            np.roll(diffim2, 4, 0), np.roll(diffim2, -4, 0), np.roll(diffim2, 4, 1), np.roll(diffim2, -4, 1),
            np.roll(diffim2, 5, 0), np.roll(diffim2, -5, 0), np.roll(diffim2, 5, 1), np.roll(diffim2, -5, 1),
        ]
        shifted_imgs2 = np.vstack([i.flatten() for i in shifted_imgs2])
    out = np.cov(shifted_imgs, shifted_imgs2, bias=1)
    tmp2 = out.copy()
    np.fill_diagonal(tmp2, np.NaN)
    stat = np.nansum(tmp2)/np.sum(np.diag(out))  # print sum of off-diag / sum of diag
    return out, stat


def alPsfMatchingKernelToArray(psfMatchingKernel, subtractedExposure):
    spatialKernel = psfMatchingKernel
    kimg = afwImage.ImageD(spatialKernel.getDimensions())
    bbox = subtractedExposure.getBBox()
    xcen = (bbox.getBeginX() + bbox.getEndX()) / 2.
    ycen = (bbox.getBeginY() + bbox.getEndY()) / 2.
    spatialKernel.computeImage(kimg, True, xcen, ycen)
    return kimg.getArray()

# Compute ALZC correction kernel from matching kernel
# Here we use a constant kernel, just compute it for the center of the image.
def performALZCExposureCorrection(templateExposure, exposure, subtractedExposure, psfMatchingKernel, log):
    import lsst.meas.algorithms as measAlg

    kimg = alPsfMatchingKernelToArray(psfMatchingKernel, subtractedExposure)
    # Compute the images' sigmas (sqrt of variance)
    sig1 = templateExposure.getMaskedImage().getVariance().getArray()
    sig2 = exposure.getMaskedImage().getVariance().getArray()
    sig1squared, _, _, _ = computeClippedImageStats(sig1)
    sig2squared, _, _, _ = computeClippedImageStats(sig2)
    corrKernel = computeDecorrelationKernel(kimg, sig1squared, sig2squared)
    # Eventually, use afwMath.convolve(), but for now just use scipy.
    log.info("ALZC: Convolving.")
    pci, _ = doConvolve(subtractedExposure.getMaskedImage().getImage().getArray(),
                        corrKernel)
    subtractedExposure.getMaskedImage().getImage().getArray()[:, :] = pci
    log.info("ALZC: Finished with convolution.")

    # Compute the subtracted exposure's updated psf
    psf = subtractedExposure.getPsf().computeImage().getArray()
    psfc = computeCorrectedDiffimPsf(corrKernel, psf, svar=sig1squared, tvar=sig2squared)
    psfcI = afwImage.ImageD(subtractedExposure.getPsf().computeImage().getBBox())
    psfcI.getArray()[:, :] = psfc
    psfcK = afwMath.FixedKernel(psfcI)
    psfNew = measAlg.KernelPsf(psfcK)
    subtractedExposure.setPsf(psfNew)
    return subtractedExposure, corrKernel


def computeClippedAfwStats(im, numSigmaClip=3., numIter=3, maskIm=None):
    """! Utility function for sigma-clipped array statistics on an image or exposure.
    @param im An afw.Exposure, masked image, or image.
    @return sigma-clipped mean, std, and variance of input array
    """
    statsControl = afwMath.StatisticsControl()
    statsControl.setNumSigmaClip(numSigmaClip)
    statsControl.setNumIter(numIter)
    ignoreMaskPlanes = ["INTRP", "EDGE", "DETECTED", "SAT", "CR", "BAD", "NO_DATA", "DETECTED_NEGATIVE"]
    statsControl.setAndMask(afwImage.MaskU.getPlaneBitMask(ignoreMaskPlanes))
    if maskIm is None:
        statObj = afwMath.makeStatistics(im,
                                         afwMath.MEANCLIP | afwMath.STDEVCLIP | afwMath.VARIANCECLIP,
                                         statsControl)
    else:
        statObj = afwMath.makeStatistics(im, maskIm,
                                         afwMath.MEANCLIP | afwMath.STDEVCLIP | afwMath.VARIANCECLIP,
                                         statsControl)
    mean = statObj.getValue(afwMath.MEANCLIP)
    std = statObj.getValue(afwMath.STDEVCLIP)
    var = statObj.getValue(afwMath.VARIANCECLIP)
    return mean, std, var


def doConvolve(exposure, kernel, use_scipy=False):
    """! Convolve an Exposure with a decorrelation convolution kernel.
    @param exposure Input afw.image.Exposure to be convolved.
    @param kernel Input 2-d numpy.array to convolve the image with
    @param use_scipy Use scipy to do convolution instead of afwMath
    @return a new Exposure with the convolved pixels and the (possibly
    re-centered) kernel.

    @note We use afwMath.convolve() but keep scipy.convolve for debugging.
    @note We re-center the kernel if necessary and return the possibly re-centered kernel
    """
    outExp = kern = None
    fkernel = fixEvenKernel(kernel)
    if use_scipy:
        pci = scipy.ndimage.filters.convolve(exposure.getMaskedImage().getImage().getArray(),
                                             fkernel, mode='constant', cval=np.nan)
        outExp = exposure.clone()
        outExp.getMaskedImage().getImage().getArray()[:, :] = pci
        kern = fkernel

    else:
        kernelImg = afwImage.ImageD(fkernel.shape[0], fkernel.shape[1])
        kernelImg.getArray()[:, :] = fkernel
        kern = afwMath.FixedKernel(kernelImg)
        maxloc = np.unravel_index(np.argmax(fkernel), fkernel.shape)
        kern.setCtrX(maxloc[0])
        kern.setCtrY(maxloc[1])
        outExp = exposure.clone()  # Do this to keep WCS, PSF, masks, etc.
        convCntrl = afwMath.ConvolutionControl(False, True, 0)
        afwMath.convolve(outExp.getMaskedImage(), exposure.getMaskedImage(), kern, convCntrl)

    return outExp, kern

# Code taken from https://github.com/lsst-dm/dmtn-006/blob/master/python/diasource_mosaic.py
def mosaicDIASources(repo_dir, visitid, ccdnum=10, cutout_size=30,
                     template_catalog=None, xnear=None, ynear=None, sourceIds=None, gridSpec=[7, 4],
                     dipoleFlag='ip_diffim_ClassificationDipole_value'):
    import matplotlib.pyplot as plt
    import matplotlib
    matplotlib.style.use('ggplot')
    import matplotlib.gridspec as gridspec
    import lsst.daf.persistence as dafPersist

    #
    # This matches up which exposures were differenced against which templates,
    # and is purely specific to this particular set of data.
    if template_catalog is None:
        template_catalog = {197790: [197802, 198372, 198376, 198380, 198384],
                            197662: [198668, 199009, 199021, 199033],
                            197408: [197400, 197404, 197412],
                            197384: [197388, 197392],
                            197371: [197367, 197375, 197379]}
    # Need to invert this to template_visit_catalog[exposure] = template
    template_visit_catalog = {}
    for templateid, visits in template_catalog.iteritems():
        for visit in visits:
            template_visit_catalog[visit] = templateid

    def make_cutout(img, x, y, cutout_size=20):
        return img[(x-cutout_size//2):(x+cutout_size//2), (y-cutout_size//2):(y+cutout_size//2)]

    def group_items(items, group_length):
        for n in xrange(0, len(items), group_length):
            yield items[n:(n+group_length)]

    b = dafPersist.Butler(repo_dir)

    template_visit = template_visit_catalog[visitid]
    templateExposure = b.get("calexp", visit=template_visit, ccdnum=ccdnum, immediate=True)
    template_img, _, _ = templateExposure.getMaskedImage().getArrays()
    template_wcs = templateExposure.getWcs()

    sourceExposure = b.get("calexp", visit=visitid, ccdnum=ccdnum, immediate=True)
    source_img, _, _ = sourceExposure.getMaskedImage().getArrays()

    subtractedExposure = b.get("deepDiff_differenceExp", visit=visitid, ccdnum=ccdnum, immediate=True)
    subtracted_img, _, _ = subtractedExposure.getMaskedImage().getArrays()
    subtracted_wcs = subtractedExposure.getWcs()

    diaSources = b.get("deepDiff_diaSrc", visit=visitid, ccdnum=ccdnum, immediate=True)

    masked_img = subtractedExposure.getMaskedImage()
    img_arr, mask_arr, var_arr = masked_img.getArrays()
    z1, z2 = zscale_image(img_arr)

    top_level_grid = gridspec.GridSpec(gridSpec[0], gridSpec[1])

    source_ind = 0
    for source_n, source in enumerate(diaSources):

        source_id = source.getId()
        if sourceIds is not None and not np.in1d(source_id, sourceIds)[0]:
            continue

        source_x = source.get("ip_diffim_NaiveDipoleCentroid_x")
        source_y = source.get("ip_diffim_NaiveDipoleCentroid_y")
        if xnear is not None and not np.any(np.abs(source_x - xnear) <= cutout_size):
            continue
        if ynear is not None and not np.any(np.abs(source_y - ynear) <= cutout_size):
            continue

        #is_dipole = source.get("ip_diffim_ClassificationDipole_value") == 1
        dipoleLabel = ''
        if source.get(dipoleFlag) == 1:
            dipoleLabel = 'Dipole'
        if source.get("ip_diffim_DipoleFit_flag_classificationAttempted") == 1:
            dipoleLabel += ' *'
        template_xycoord = template_wcs.skyToPixel(subtracted_wcs.pixelToSky(source_x, source_y))
        cutouts = [make_cutout(template_img, template_xycoord.getY(), template_xycoord.getX(),
                               cutout_size=cutout_size),
                   make_cutout(source_img, source_y, source_x, cutout_size=cutout_size),
                   make_cutout(subtracted_img, source_y, source_x, cutout_size=cutout_size)]

        try:
            subgrid = gridspec.GridSpecFromSubplotSpec(1, 3, subplot_spec=top_level_grid[source_ind],
                                                       wspace=0)
        except:
            continue
        for cutout_n, cutout in enumerate(cutouts):
            plt.subplot(subgrid[0, cutout_n])
            plt.imshow(cutout, vmin=z1, vmax=z2, cmap=plt.cm.gray)
            plt.gca().xaxis.set_ticklabels([])
            plt.gca().yaxis.set_ticklabels([])

        plt.subplot(subgrid[0, 0])
        source_ind += 1
        #if is_dipole:
        #print(source_n, source_id)
        plt.ylabel(str(source_n) + dipoleLabel)


# Updated ALZC kernel and PSF computation (from ip_diffim.imageDecorrelation)
# This should eventually replace computeCorrectionKernelALZC and
# computeCorrectedDiffimPsfALZC

def computeDecorrelationKernel(kappa, svar=0.04, tvar=0.04, preConvKernel=None, delta=0.):
    """! Compute the Lupton/ZOGY post-conv. kernel for decorrelating an
    image difference, based on the PSF-matching kernel.
    @param kappa  A matching kernel 2-d numpy.array derived from Alard & Lupton PSF matching
    @param svar   Average variance of science image used for PSF matching
    @param tvar   Average variance of template image used for PSF matching
    @param preConvKernel   A pre-convolution kernel applied to im2 prior to A&L PSF matching
    @return a 2-d numpy.array containing the correction kernel

    @note As currently implemented, kappa is a static (single, non-spatially-varying) kernel.
    """
    kappa = fixOddKernel(kappa)
    kft = scipy.fftpack.fft2(kappa)
    pc = pcft = 1.0
    if preConvKernel is not None:
        pc = fixOddKernel(preConvKernel)
        pcft = scipy.fftpack.fft2(pc)

    kft = np.sqrt((svar + tvar + delta) / (svar * np.abs(pcft)**2 + tvar * np.abs(kft)**2 + delta))
    #if preConvKernel is not None:
    #    kft = scipy.fftpack.fftshift(kft)  # I can't figure out why we need to fftshift sometimes but not others.
    pck = scipy.fftpack.ifft2(kft)
    #if np.argmax(pck.real) == 0:  # I can't figure out why we need to ifftshift sometimes but not others.
    #    pck = scipy.fftpack.ifftshift(pck.real)
    fkernel = fixEvenKernel(pck.real)

    # I think we may need to "reverse" the PSF, as in the ZOGY (and Kaiser) papers...
    # This is the same as taking the complex conjugate in Fourier space before FFT-ing back to real space.
    if False:  # TBD: figure this out. For now, we are turning it off.
        fkernel = fkernel[::-1, :]

    return fkernel

def computeCorrectedDiffimPsf(kappa, psf, svar=0.04, tvar=0.04):
    """! Compute the (decorrelated) difference image's new PSF.
    new_psf = psf(k) * sqrt((svar + tvar) / (svar + tvar * kappa_ft(k)**2))

    @param kappa  A matching kernel array derived from Alard & Lupton PSF matching
    @param psf    The uncorrected psf array of the science image (and also of the diffim)
    @param svar   Average variance of science image used for PSF matching
    @param tvar   Average variance of template image used for PSF matching
    @return a 2-d numpy.array containing the new PSF
    """
    def post_conv_psf_ft2(psf, kernel, svar, tvar):
        # Pad psf or kernel symmetrically to make them the same size!
        # Note this assumes they are both square (width == height)
        if psf.shape[0] < kernel.shape[0]:
            diff = (kernel.shape[0] - psf.shape[0]) // 2
            psf = np.pad(psf, (diff, diff), mode='constant')
        elif psf.shape[0] > kernel.shape[0]:
            diff = (psf.shape[0] - kernel.shape[0]) // 2
            kernel = np.pad(kernel, (diff, diff), mode='constant')

        psf = fixOddKernel(psf)
        psf_ft = scipy.fftpack.fft2(psf)
        kernel = fixOddKernel(kernel)
        kft = scipy.fftpack.fft2(kernel)
        out = psf_ft * np.sqrt((svar + tvar) / (svar + tvar * kft**2))
        return out

    def post_conv_psf(psf, kernel, svar, tvar):
        kft = post_conv_psf_ft2(psf, kernel, svar, tvar)
        out = scipy.fftpack.ifft2(kft)
        return out

    pcf = post_conv_psf(psf=psf, kernel=kappa, svar=svar, tvar=tvar)
    pcf = pcf.real / pcf.real.sum()
    return pcf

def fixOddKernel(kernel):
    """! Take a kernel with odd dimensions and make them even for FFT

    @param kernel a numpy.array
    @return a fixed kernel numpy.array. Returns a copy if the dimensions needed to change;
    otherwise just return the input kernel.
    """
    # Note this works best for the FFT if we left-pad
    out = kernel
    changed = False
    if (out.shape[0] % 2) == 1:
        out = np.pad(out, ((1, 0), (0, 0)), mode='constant')
        changed = True
    if (out.shape[1] % 2) == 1:
        out = np.pad(out, ((0, 0), (1, 0)), mode='constant')
        changed = True
    if changed:
        out *= (np.mean(kernel) / np.mean(out))  # need to re-scale to same mean for FFT
    return out

def fixEvenKernel(kernel):
    """! Take a kernel with even dimensions and make them odd, centered correctly.
    @param kernel a numpy.array
    @return a fixed kernel numpy.array
    """
    # Make sure the peak (close to a delta-function) is in the center!
    maxloc = np.unravel_index(np.argmax(kernel), kernel.shape)
    out = np.roll(kernel, kernel.shape[0]//2 - maxloc[0], axis=0)
    out = np.roll(out, out.shape[1]//2 - maxloc[1], axis=1)
    # Make sure it is odd-dimensioned by trimming it.
    if (out.shape[0] % 2) == 0:
        maxloc = np.unravel_index(np.argmax(out), out.shape)
        if out.shape[0] - maxloc[0] > maxloc[0]:
            out = out[:-1, :]
        else:
            out = out[1:, :]
        if out.shape[1] - maxloc[1] > maxloc[1]:
            out = out[:, :-1]
        else:
            out = out[:, 1:]
    return out


class Exposure(object):
    def __init__(self, im, psf=None, var=None, metaData=None):
        self.im = im
        self.psf = psf
        self.var = var
        self.metaData = {} if metaData is None else metaData
        if var is not None:
            self.sig, _, _, _ = np.sqrt(computeClippedImageStats(var))
        else:
            _, self.sig, _, _ = computeClippedImageStats(im)

    def setMetaData(self, key, value):
        self.metaData[key] = value

    def asAfwExposure(self):
        try:
            import lsst.afw.image as afwImage
            import lsst.afw.geom as afwGeom
            import lsst.meas.algorithms as measAlg
        except Exception as e:
            print e
            return None

        bbox = afwGeom.Box2I(afwGeom.Point2I(0, 0), afwGeom.Point2I(self.im.shape[0]-1, self.im.shape[1]-1))
        im1ex = afwImage.ExposureF(bbox)
        im1ex.getMaskedImage().getImage().getArray()[:, :] = self.im
        im1ex.getMaskedImage().getVariance().getArray()[:, :] = self.var
        psfShape = self.psf.shape[0]//2
        psfBox = afwGeom.Box2I(afwGeom.Point2I(-psfShape, -psfShape), afwGeom.Point2I(psfShape, psfShape))
        psf = afwImage.ImageD(psfBox)
        psf.getArray()[:, :] = self.psf
        psfK = afwMath.FixedKernel(psf)
        psfNew = measAlg.KernelPsf(psfK)
        im1ex.setPsf(psfNew)
        wcs = makeWcs()
        im1ex.setWcs(wcs)
        return im1ex

    def doDetection(self, threshold=5.0, doSmooth=True):
        return doDetection(self.asAfwExposure(), threshold=threshold, doSmooth=doSmooth)

    def doMeasurePsf(self):
        res = measurePsf(self.asAfwExposure())
        self.psf = res.psf.computeImage()


def makeWcs(offset=0):  # Taken from IP_DIFFIM/tests/testImagePsfMatch.py
    import lsst.daf.base as dafBase
    metadata = dafBase.PropertySet()
    metadata.set("SIMPLE", "T")
    metadata.set("BITPIX", -32)
    metadata.set("NAXIS", 2)
    metadata.set("NAXIS1", 1024)
    metadata.set("NAXIS2", 1153)
    metadata.set("RADECSYS", 'FK5')
    metadata.set("EQUINOX", 2000.)
    metadata.setDouble("CRVAL1", 215.604025685476)
    metadata.setDouble("CRVAL2", 53.1595451514076)
    metadata.setDouble("CRPIX1", 1109.99981456774 + offset)
    metadata.setDouble("CRPIX2", 560.018167811613 + offset)
    metadata.set("CTYPE1", 'RA---SIN')
    metadata.set("CTYPE2", 'DEC--SIN')
    metadata.setDouble("CD1_1", 5.10808596133527E-05)
    metadata.setDouble("CD1_2", 1.85579539217196E-07)
    metadata.setDouble("CD2_2", -5.10281493481982E-05)
    metadata.setDouble("CD2_1", -8.27440751733828E-07)
    return afwImage.makeWcs(metadata)


def doDetection(exp, threshold=5.0, thresholdType='stdev', thresholdPolarity='both', doSmooth=True,
                asDF=True):
    # Modeled from meas_algorithms/tests/testMeasure.py
    import lsst.meas.algorithms as measAlg
    import lsst.meas.base as measBase
    import lsst.afw.table as afwTable
    import lsst.log

    schema = afwTable.SourceTable.makeMinimalSchema()
    config = measAlg.SourceDetectionTask.ConfigClass()
    config.thresholdPolarity = thresholdPolarity
    config.reEstimateBackground = False
    config.thresholdValue = threshold
    config.thresholdType = thresholdType
    detectionTask = measAlg.SourceDetectionTask(config=config, schema=schema)
    detectionTask.log.setLevel(log_level)

    # Do measurement too, so we can get x- and y-coord centroids

    config = measBase.SingleFrameMeasurementTask.ConfigClass()
    # Use the minimum set of plugins required.
    config.plugins = ["base_CircularApertureFlux",
                      "base_PixelFlags",
                      "base_SkyCoord",
                      "base_PsfFlux",
                      "base_GaussianCentroid",
                      "base_GaussianFlux",
                      "base_PeakLikelihoodFlux",
                      "base_PeakCentroid",
                      "base_SdssCentroid",
                      "base_SdssShape",
                      "base_NaiveCentroid",
                      #"ip_diffim_NaiveDipoleCentroid",
                      #"ip_diffim_NaiveDipoleFlux",
                      "ip_diffim_PsfDipoleFlux",
                      "ip_diffim_ClassificationDipole",
                      ]
    config.slots.centroid = "base_GaussianCentroid" #"ip_diffim_NaiveDipoleCentroid"
    config.slots.calibFlux = None
    config.slots.modelFlux = None
    config.slots.instFlux = None
    config.slots.shape = "base_SdssShape"
    config.doReplaceWithNoise = False
    measureTask = measBase.SingleFrameMeasurementTask(schema, config=config)
    measureTask.log.setLevel(log_level)

    table = afwTable.SourceTable.make(schema)
    sources = detectionTask.run(table, exp, doSmooth=doSmooth).sources

    measureTask.measure(exp, sources)

    if asDF:
        import pandas as pd
        sources = pd.DataFrame({col: sources.columns[col] for col in sources.schema.getNames()})

    return sources

def measurePsf(exp, measurePsfAlg='psfex'):
    import lsst.pipe.tasks.measurePsf as measurePsf
    import lsst.afw.table as afwTable
    import lsst.ip.diffim as ipDiffim  # for detection - needs NaiveDipoleCentroid (registered by my routine)
    import lsst.meas.algorithms        as measAlg
    import lsst.log

    # The old (meas_algorithms) SdssCentroid assumed this by default if it
    # wasn't specified; meas_base requires us to be explicit.
    shape = exp.getPsf().computeImage().getDimensions()
    psf = measAlg.DoubleGaussianPsf(shape[0], shape[1], 0.01)
    exp.setPsf(psf)

    im = exp.getMaskedImage().getImage()
    im -= np.median(im.getArray())

    sources = doDetection(exp, asDF=False)
    config = measurePsf.MeasurePsfConfig()
    schema = afwTable.SourceTable.makeMinimalSchema()

    if measurePsfAlg is 'psfex':
        try:
            import lsst.meas.extensions.psfex.psfexPsfDeterminer
            config.psfDeterminer['psfex'].spatialOrder = 2  # 2 is default, 0 seems to kill it
            config.psfDeterminer['psfex'].recentroid = True
            config.psfDeterminer.name = 'psfex'
        except ImportError as e:
            print "WARNING: Unable to use psfex: %s" % e
            measurePsfAlg = 'pca'

    if measurePsfAlg is 'pca':
        config.psfDeterminer['pca'].sizeCellX = 128
        config.psfDeterminer['pca'].sizeCellY = 128
        config.psfDeterminer['pca'].spatialOrder = 1
        config.psfDeterminer['pca'].nEigenComponents = 3
        config.psfDeterminer.name = "pca"

    psfDeterminer = config.psfDeterminer.apply()
    #print type(psfDeterminer)
    task = measurePsf.MeasurePsfTask(schema=schema, config=config)
    task.log.setLevel(log_level)
    result = task.run(exp, sources)
    return result

# Compute mean of variance plane. Can actually get std of image plane if
# actuallyDoImage=True and statToDo=afwMath.VARIANCECLIP
def computeVarianceMean(exposure, actuallyDoImage=False, statToDo=afwMath.MEANCLIP):
    try:
        import lsst.afw.math as afwMath
    except Exception as e:
        print e
        return None
    statsControl = afwMath.StatisticsControl()
    statsControl.setNumSigmaClip(3.)
    statsControl.setNumIter(3)
    ignoreMaskPlanes = ("INTRP", "EDGE", "DETECTED", "SAT", "CR", "BAD", "NO_DATA", "DETECTED_NEGATIVE")
    statsControl.setAndMask(afwImage.MaskU.getPlaneBitMask(ignoreMaskPlanes))
    imToDo = exposure.getMaskedImage().getVariance()
    if actuallyDoImage:
        imToDo = exposure.getMaskedImage().getImage()
    statObj = afwMath.makeStatistics(imToDo, exposure.getMaskedImage().getMask(),
                                     statToDo, statsControl)
    var = statObj.getValue(statToDo)
    return var


class DiffimTest(object):
    def __init__(self, doInit=True, **kwargs):
        self.args = kwargs

        if doInit:
            # Generate images and PSF's with the same dimension as the image (used for A&L)
            im1, im2, P_r, P_n, im1_var, im2_var, self.centroids, \
                self.changedCentroidInd = makeFakeImages(**kwargs)

            self.kwargs = kwargs

            self.im1 = Exposure(im1, P_r, im1_var)
            self.im1.setMetaData('sky', kwargs.get('sky', 300.))

            self.im2 = Exposure(im2, P_n, im2_var)
            self.im2.setMetaData('sky', kwargs.get('sky', 300.))

            self.astrometricOffsets = kwargs.get('offset', [0, 0])
            try:
                dx, dy = self.computeAstrometricOffsets(threshold=0.25)
                self.astrometricOffsets = [dx, dy]
            except Exception as e:
                pass

            self.D_AL = self.kappa = self.D_ZOGY = self.S_corr_ZOGY = self.S_ZOGY = None

    # Idea is to call test2 = test.clone(), then test2.reverseImages() to then run diffim
    # on im2-im1.
    def reverseImages(self):
        self.im1, self.im2 = self.im2, self.im1
        self.D_AL = self.kappa = self.D_ZOGY = self.S_corr_ZOGY = self.S_ZOGY = None

    def clone(self):
        out = DiffimTest(imSize=self.im1.im.shape, sky=self.im1.metaData['sky'],
                         doInit=False)
        out.kwargs = self.kwargs
        out.im1, out.im2 = self.im1, self.im2
        out.centroids, out.changedCentroidInd = self.centroids, self.changedCentroidInd
        out.astrometricOffsets = self.astrometricOffsets
        out.D_AL, out.kappa, out.D_ZOGY, \
            out.S_corr_ZOGY, out.S_ZOGY = self.D_AL, self.kappa, self.D_ZOGY, \
                                          self.S_corr_ZOGY, self.S_ZOGY
        return out

    def doAL(self, spatialKernelOrder=0, spatialBackgroundOrder=1, kernelSize=None, doDecorr=True,
             doPreConv=False, betaGauss=1.):
        if kernelSize is None:
            #if not doPreConv:
            kernelSize = self.im1.psf.shape[0]//2+1  # Hastily assume all PSFs are same sized and square
            #else:
            #    kernelSize = np.floor(self.im1.psf.shape[0] * np.sqrt(2.)).astype(int)//2
            #    if kernelSize % 2 == 0:  # make odd-sized
            #        kernelSize -= 1
        preConvKernel = None
        if doPreConv:
            preConvKernel = self.im2.psf
            if betaGauss == 1.:  # update default, resize the kernel appropriately
                betaGauss = 1./np.sqrt(2.)
        D_AL, D_psf, self.kappa_AL = performAlardLupton(self.im1.im, self.im2.im,
                                                        spatialKernelOrder=spatialKernelOrder,
                                                        spatialBackgroundOrder=spatialBackgroundOrder,
                                                        sig1=self.im1.sig, sig2=self.im2.sig,
                                                        kernelSize=kernelSize,
                                                        betaGauss=betaGauss,
                                                        doALZCcorrection=doDecorr,
                                                        im2Psf=self.im2.psf,
                                                        preConvKernel=preConvKernel)
        # This is not entirely correct, we also need to convolve var with the decorrelation kernel (squared):
        var = self.im1.var + scipy.ndimage.filters.convolve(self.im2.var, self.kappa_AL**2., mode='constant')
        self.D_AL = Exposure(D_AL, D_psf, var)
        self.D_AL.im /= np.sqrt(self.im1.metaData['sky'] + self.im2.metaData['sky'])  #np.sqrt(var)
        self.D_AL.var /= np.sqrt(self.im1.metaData['sky'] + self.im2.metaData['sky'])  #np.sqrt(var)
        # TBD: make the returned D an Exposure.
        return self.D_AL, self.kappa_AL

    def computeAstrometricOffsets(self, threshold=0.5):
        src1 = self.im1.doDetection()
        src1 = src1[~src1['base_PsfFlux_flag']]
        src1 = src1[['base_NaiveCentroid_x', 'base_NaiveCentroid_y']]
        src1.reindex()
        src2 = self.im2.doDetection()
        src2 = src2[~src2['base_PsfFlux_flag']]
        src2 = src2[['base_NaiveCentroid_x', 'base_NaiveCentroid_y']]
        src2.reindex()
        dx, dy, _ = computeOffset(src1, src2, threshold=threshold)
        return dx, dy

    def doZOGY(self, computeScorr=True, inImageSpace=True):
        D_ZOGY = None
        if inImageSpace:
            D_ZOGY = performZOGYImageSpace(self.im1.im, self.im2.im, self.im1.psf, self.im2.psf,
                                           sig1=self.im1.sig, sig2=self.im2.sig)
        else:  # Do all in fourier space (needs image-sized PSFs)
            padSize0 = self.im1.im.shape[0]//2 - self.im1.psf.shape[0]//2
            padSize1 = self.im1.im.shape[1]//2 - self.im1.psf.shape[1]//2
            # Hastily assume the image is even-sized and the psf is odd...
            psf1 = np.pad(self.im1.psf, ((padSize0-1, padSize0), (padSize1-1, padSize1)), mode='constant',
                          constant_values=0)
            psf2 = np.pad(self.im2.psf, ((padSize0-1, padSize0), (padSize1-1, padSize1)), mode='constant',
                          constant_values=0)
            D_ZOGY = performZOGY(self.im1.im, self.im2.im, psf1, psf2,
                                 sig1=self.im1.sig, sig2=self.im2.sig)

        P_D_ZOGY, F_D = computeZOGYDiffimPsf(self.im1.im, self.im2.im,
                                             self.im1.psf, self.im2.psf,
                                             sig1=self.im1.sig, sig2=self.im2.sig, F_r=1., F_n=1.)
        self.D_ZOGY = Exposure(D_ZOGY, P_D_ZOGY, self.im1.var + self.im2.var)

        if computeScorr:
            S_corr_ZOGY, S_ZOGY, _, P_D_ZOGY, F_D, var1c, \
                var2c = performZOGY_Scorr(self.im1.im, self.im2.im, self.im1.var, self.im2.var,
                                          sig1=self.im1.sig, sig2=self.im2.sig,
                                          im1_psf=self.im1.psf, im2_psf=self.im2.psf,
                                          D=D_ZOGY, #xVarAst=dx, yVarAst=dy)
                                          xVarAst=self.astrometricOffsets[0], #**2.,
                                          yVarAst=self.astrometricOffsets[1]) #**2.)
            self.S_ZOGY = Exposure(S_ZOGY, P_D_ZOGY, np.sqrt(var1c + var2c))
            self.S_corr_ZOGY = Exposure(S_corr_ZOGY, P_D_ZOGY, np.sqrt(var1c + var2c)/np.sqrt(var1c + var2c))

        return self.D_ZOGY

    def doALInStack(self, doWarping=False, doDecorr=True, doPreConv=False):
        import lsst.ip.diffim as ipDiffim
        import lsst.meas.algorithms as measAlg
        import lsst.log

        im1 = self.im1.asAfwExposure()
        im2 = self.im2.asAfwExposure()

        preConvKernel = None
        im2c = im2
        if doPreConv:
            #doDecorr = False  # Right now decorr with pre-conv doesn't work
            preConvKernel = self.im2.psf
            im2c, kern = doConvolve(im2, preConvKernel, use_scipy=False)

        config = ipDiffim.ImagePsfMatchTask.ConfigClass()
        config.kernel.name = "AL"
        subconfig = config.kernel.active
        config.kernel.active.spatialKernelOrder = 1
        config.kernel.active.spatialBgOrder = 0
        subconfig.afwBackgroundConfig.useApprox = False
        subconfig.constantVarianceWeighting = False
        subconfig.singleKernelClipping = False
        subconfig.spatialKernelClipping = False
        subconfig.fitForBackground = False

        task = ipDiffim.ImagePsfMatchTask(config=config)
        task.log.setLevel(log_level)
        result = task.subtractExposures(im1, im2c, doWarping=doWarping)

        if doDecorr:
            kimg = alPsfMatchingKernelToArray(result.psfMatchingKernel, im1)
            #return kimg
            if preConvKernel is not None and kimg.shape[0] < preConvKernel.shape[0]:
                # This is likely brittle and may only work if both kernels are odd-shaped.
                #kimg[np.abs(kimg) < 1e-4] = np.sign(kimg)[np.abs(kimg) < 1e-4] * 1e-8
                #kimg -= kimg[0, 0]
                padSize0 = preConvKernel.shape[0]//2 - kimg.shape[0]//2
                padSize1 = preConvKernel.shape[1]//2 - kimg.shape[1]//2
                kimg = np.pad(kimg, ((padSize0, padSize0), (padSize1, padSize1)), mode='constant',
                              constant_values=0)
                #kimg /= kimg.sum()

                #preConvKernel = preConvKernel[padSize0:-padSize0, padSize1:-padSize1]
                #print kimg.shape, preConvKernel.shape

            sig1squared = computeVarianceMean(im1)
            sig2squared = computeVarianceMean(im2)
            pck = computeDecorrelationKernel(kimg, sig1squared, sig2squared,
                                             preConvKernel=preConvKernel, delta=1.)
            #return kimg, preConvKernel, pck
            diffim, _ = doConvolve(result.subtractedExposure, pck, use_scipy=False)
            #diffim.getMaskedImage().getImage().getArray()[:, ] \
            #    /= np.sqrt(self.im1.metaData['sky'] + self.im1.metaData['sky'])
            #diffim.getMaskedImage().getVariance().getArray()[:, ] \
            #    /= np.sqrt(self.im1.metaData['sky'] + self.im1.metaData['sky'])

            psf = result.subtractedExposure.getPsf().computeImage().getArray()
            # NOTE! Need to compute the updated PSF including preConvKernel !!! This doesn't do it:
            psfc = computeCorrectedDiffimPsf(kimg, psf, svar=sig1squared, tvar=sig2squared)
            psfcI = afwImage.ImageD(psfc.shape[0], psfc.shape[1])
            psfcI.getArray()[:, :] = psfc
            psfcK = afwMath.FixedKernel(psfcI)
            psfNew = measAlg.KernelPsf(psfcK)
            diffim.setPsf(psfNew)

            result.decorrelatedDiffim = diffim
            result.preConvKernel = preConvKernel
            result.decorrelationKernel = pck
            result.kappaImg = kimg

        return result

    def runTest(self, subtractMethods=['ALstack', 'ZOGY', 'ZOGY_S', 'ALstack_noDecorr'],
                returnSources=False):
        import pandas as pd  # We're going to store the results as pandas dataframes.

        D_ZOGY = S_ZOGY = res = D_AL = None
        src = {}
        # Run diffim first
        for subMethod in subtractMethods:
            if subMethod is 'ALstack' or subMethod is 'ALstack_noDecorr':
                res = self.res = self.doALInStack(doPreConv=False, doDecorr=True)
            if subMethod is 'ZOGY_S':
                if self.S_corr_ZOGY is None:
                    self.doZOGY(computeScorr=True)
                S_ZOGY = self.S_corr_ZOGY
            if subMethod is 'ZOGY':
                if self.D_ZOGY is None:
                    self.doZOGY(computeScorr=True)
                D_ZOGY = self.D_ZOGY
            if subMethod is 'AL':  # my clean-room (pure python) version of A&L
                try:
                    self.doAL(spatialKernelOrder=0, spatialBackgroundOrder=1)
                    D_AL = self.D_AL
                except:
                    D_AL = None

            # Run detection next
            try:
                if subMethod is 'ALstack':
                    src_AL = doDetection(res.decorrelatedDiffim)
                    src_AL = src_AL[~src_AL['base_PsfFlux_flag']]
                    src['ALstack'] = src_AL
                elif subMethod is 'ALstack_noDecorr':
                    src_AL2 = doDetection(res.subtractedExposure)
                    src_AL2 = src_AL2[~src_AL2['base_PsfFlux_flag']]
                    src['ALstack_noDecorr'] = src_AL2
                elif subMethod is 'ZOGY':
                    src_ZOGY = doDetection(D_ZOGY.asAfwExposure())
                    src_ZOGY = src_ZOGY[~src_ZOGY['base_PsfFlux_flag']]
                    src['ZOGY'] = src_ZOGY
                elif subMethod is 'ZOGY_S':
                    src_SZOGY = doDetection(S_ZOGY.asAfwExposure(), doSmooth=False)
                    src_SZOGY = src_SZOGY[~src_SZOGY['base_PsfFlux_flag']]
                    src['SZOGY'] = src_SZOGY
                elif subMethod is 'AL' and D_AL is not None:
                    src_AL = doDetection(D_AL.asAfwExposure())
                    src_AL = src_AL[~src_AL['base_PsfFlux_flag']]
                    src['AL'] = src_AL
            except Exception as e:
                print(e)
                pass

        if returnSources:
            return src

        # Compare detections to input sources and get true positives and false negatives
        changedCentroid = np.array(self.centroids[self.changedCentroidInd, :])

        detections = {}
        for key in src:
            dist = np.sqrt(np.add.outer(src[key].base_NaiveCentroid_x, -changedCentroid[:, 0])**2. + \
               np.add.outer(src[key].base_NaiveCentroid_y, -changedCentroid[:, 1])**2.) # in pixels
            matches = np.where(dist <= 1.5)
            true_pos = len(np.unique(matches[0]))
            false_neg = changedCentroid.shape[0] - len(np.unique(matches[1]))
            false_pos = src[key].shape[0] - len(np.unique(matches[0]))
            detections[key] = {'TP': true_pos, 'FN': false_neg, 'FP': false_pos}

        return detections

