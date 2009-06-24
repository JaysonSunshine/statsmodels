import numpy as np
from numpy.linalg import inv
#from scipy import optimize

from scipy.stats import t, z

from nipy.fixes.scipy.stats.models.contrast import ContrastResults
from nipy.fixes.scipy.stats.models.utils import recipr
#from .models.contrast import ContrastResults
#from .modles.utils import recipr
# having trouble with relative imports
# because I often run tests from inside the directory?

import numpy.lib.recfunctions as nprf

class Model(object):
    """
    A (predictive) statistical model. The class Model itself does nothing
    but lays out the methods expected of any subclass.
    """

    _results = None

    def fit(self):
        """
        Fit a model to data.
        """
        raise NotImplementedError

    def predict(self, exogs):
        """
        After a model has been fit, results are (assumed to be) stored
        in self.results, which itself should have a predict method.
        """
        self.results.predict(exogs)

class LikelihoodModel(Model):

    def __init__(self, endog, exog=None):
        self._endog = endog
        self._exog = exog
        self.initialize()
# note see original for easier

    def initialize(self):
        """
        Initialize (possibly re-initialize) a Model instance. For
        instance, the design matrix of a linear model may change
        and some things must be recomputed.
        """
        pass

    def llf(self, theta):
        """
        Log-likelihood of model.
        """
        raise NotImplementedError

    def score(self, theta):
        """
        Score function of model = gradient of logL with respect to
        theta.
        """
        raise NotImplementedError

    def information(self, theta):
        """
        Fisher information function of model = - Hessian of logL with respect
        to theta.
        """
        raise NotImplementedError

    def fit(self, theta, method='newton'):
        if method is 'newton':
            results = self.newton(theta)
        else:
            raise ValueError("Unknown fit method.")
        self._results = results

    def newton(self, theta):
        def f(theta): return -self.llf(theta)
        xopt, fopt, iter, funcalls, warnflag =\
          optimize.fmin(f, theta, full_output=True)
        converge = not warnflag
        extras = dict(iter=iter, evaluations=funcalls, converge=converge)
        return LikelihoodModelResults(self, theta, llf=fopt, **extras)


class Results(object):
    def __init__(self, theta, **kwd):
        """
        Parameters
        ----------
        model : the estimated model
        theta : parameter estimates from estimated model
        """
#        self._model = model
        self._theta = theta
        self.__dict__.update(kwd)
        self.initialize()
    @property
    def theta(self):
        return self._theta
#    @property
#    def model(self):
#        return self._model
    def initialize(self):
        pass

class LikelihoodModelResults(Results):
    """ Class to contain results from likelihood models """
    def __init__(self, theta, normalized_cov_theta=None, scale=1.):
        """
        Parameters
        -----------
        theta : 1d array_like
            parameter estimates from estimated model
        normalized_cov_theta : 2d array
           Normalized (before scaling) covariance of thetas
            normalized_cov_thetas is also known as the hat matrix or H
            (Semiparametric regression, Ruppert, Wand, Carroll; CUP 2003)
        scale : float
            For (some subset of models) scale will typically be the
            mean square error from the estimated model (sigma^2)

        Comments
        --------

        The covariance of thetas is given by scale times
        normalized_cov_theta
        """
#        print self.__class__
        super(LikelihoodModelResults, self).__init__(theta)
        self.normalized_cov_theta = normalized_cov_theta
        self.scale = scale

    def normalized_cov_theta(self):
        raise NotImplementedError

    def scale(self):
        raise NotImplementedError

    def t(self, column=None):
        """
        Return the t-statistic for a given parameter estimate.

        Use Tcontrast for more complicated t-statistics.

        """

        if self.normalized_cov_theta is None:
            raise ValueError, 'need covariance of parameters for computing T statistics'

        if column is None:
            column = range(self.theta.shape[0])

        column = np.asarray(column)
        _theta = self.theta[column]
        _cov = self.cov_theta(column=column)
        if _cov.ndim == 2:
            _cov = np.diag(_cov)
        _t = _theta * recipr(np.sqrt(_cov))
        return _t

    def cov_theta(self, matrix=None, column=None, scale=None, other=None):
        """
        Returns the variance/covariance matrix of a linear contrast
        of the estimates of theta, multiplied by scale which
        will usually be an estimate of sigma^2.

        The covariance of
        interest is either specified as a (set of) column(s) or a matrix.
        """

        if self.normalized_cov_theta is None:
            raise ValueError, 'need covariance of parameters for computing \
(unnormalized) covariances'
        if scale is None:
            scale = self.scale
        if column is not None:
            column = np.asarray(column)
            if column.shape == ():
                return self.normalized_cov_theta[column, column] * scale
            else:
                return self.normalized_cov_theta[column][:,column] * scale
        elif matrix is not None:
            if other is None:
                other = matrix
            tmp = np.dot(matrix, np.dot(self.normalized_cov_theta, np.transpose(other)))
            return tmp * scale
        if matrix is None and column is None:
            if scale.size==1:
                scale=np.eye(len(self.resid))*scale
            return np.dot(np.dot(self.calc_theta, scale), self.calc_theta.T)

    def Tcontrast(self, matrix, t=True, sd=True, scale=None):
        """
        Compute a Tcontrast for a row vector matrix. To get the t-statistic
        for a single column, use the 't' method.
        """

        if self.normalized_cov_theta is None:
            raise ValueError, 'need covariance of parameters for computing T statistics'

        _t = _sd = None

        _effect = np.dot(matrix, self.theta)
        if sd:
            _sd = np.sqrt(self.cov_theta(matrix=matrix))
        if t:
            _t = _effect * recipr(_sd)
        return ContrastResults(effect=_effect, t=_t, sd=_sd, df_denom=self.df_resid)

    def Fcontrast(self, matrix, eff=True, t=True, sd=True, scale=None, invcov=None):
        """
        Compute an Fcontrast for a contrast matrix.

        Here, matrix M is assumed to be non-singular. More precisely,

        M pX pX' M'

        is assumed invertible. Here, pX is the generalized inverse of the
        design matrix of the model. There can be problems in non-OLS models
        where the rank of the covariance of the noise is not full.

        See the contrast module to see how to specify contrasts.
        In particular, the matrices from these contrasts will always be
        non-singular in the sense above.

        """

        if self.normalized_cov_theta is None:
            raise ValueError, 'need covariance of parameters for computing F statistics'

        ctheta = np.dot(matrix, self.theta)

        q = matrix.shape[0]
        if invcov is None:
            invcov = inv(self.cov_theta(matrix=matrix, scale=1.0))
        F = np.add.reduce(np.dot(invcov, ctheta) * ctheta, 0) * recipr((q * self.scale))
        return ContrastResults(F=F, df_denom=self.df_resid, df_num=invcov.shape[0])

    def conf_int(self, alpha=.05, cols=None):
        """
        Returns the confidence interval of the specified theta estimates.

        Parameters
        ----------
        alpha : float, optional
            The `alpha` level for the confidence interval.
            ie., `alpha` = .05 returns a 95% confidence interval.
        cols : tuple, optional
            `cols` specifies which confidence intervals to return

        Returns : array
            Each item contains [lower, upper]

        Example
        -------
        >>>import numpy as np
        >>>from numpy.random import standard_normal as stan
        >>>import nipy.fixes.scipy.stats.models as SSM
        >>>x = np.hstack((stan((30,1)),stan((30,1)),stan((30,1))))
        >>>theta=np.array([3.25, 1.5, 7.0])
        >>>y = np.dot(x,theta) + stan((30))
        >>>model = SSM.regression.OLSModel(x, hascons=False).fit(y)
        >>>model.conf_int(cols=(1,2))

        Notes
        -----
        TODO:
        tails : string, optional
            `tails` can be "two", "upper", or "lower"
        """
        if self.__class__.__name__ is 'OLSModel':
            dist = t
        if self.__class__.__name__ is 'Model': # is this always appropriate
                                               # for GLM?
            dist = z
        else:
            dist = t
        if cols is None:
            lower = self.theta - dist.ppf(1-alpha/2,self.df_resid) *\
                    np.diag(np.sqrt(self.cov_theta()))
            upper = self.theta + dist.ppf(1-alpha/2,self.df_resid) *\
                    np.diag(np.sqrt(self.cov_theta()))
        else:
            lower=[]
            upper=[]
            for i in cols:
                lower.append(self.theta[i] - dist.ppf(1-alpha/2,self.df_resid) *\
                    np.diag(np.sqrt(self.cov_theta()))[i])
                upper.append(self.theta[i] + dist.ppf(1-alpha/2,self.df_resid) *\
                    np.diag(np.sqrt(self.cov_theta()))[i])
        return np.asarray(zip(lower,upper))



