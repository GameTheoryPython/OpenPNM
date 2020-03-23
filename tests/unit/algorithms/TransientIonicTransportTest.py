import numpy as np
import openpnm as op
from openpnm.phases import mixtures


class TransientIonicTransportTest:

    def setup_class(self):
        np.random.seed(0)
        self.net = op.network.Cubic(shape=[8, 8, 1], spacing=9e-4)

        prs = (self.net['pore.back'] * self.net['pore.right']
               + self.net['pore.back'] * self.net['pore.left']
               + self.net['pore.front'] * self.net['pore.right']
               + self.net['pore.front'] * self.net['pore.left'])
        thrts = self.net['throat.surface']
        op.topotools.trim(network=self.net, pores=self.net.Ps[prs],
                          throats=self.net.Ts[thrts])

        self.geo = op.geometry.StickAndBall(network=self.net,
                                            pores=self.net.Ps,
                                            throats=self.net.Ts)
        pr_d = op.models.misc.constant
        trt_d = op.models.misc.constant
        self.geo.add_model(propname='pore.diameter', model=pr_d, value=1.5e-4)
        self.geo.add_model(propname='throat.diameter', model=trt_d, value=1e-4)
        self.geo.regenerate_models()

        self.phase = mixtures.SalineWater(network=self.net)
        # Retrieve handles to each species for use below
        self.Na, self.H2O, self.Cl = self.phase.components.values()

        # physics
        self.phys = op.physics.GenericPhysics(network=self.net,
                                              phase=self.phase,
                                              geometry=self.geo)

        flow = op.models.physics.hydraulic_conductance.hagen_poiseuille
        self.phys.add_model(propname='throat.hydraulic_conductance',
                            pore_viscosity='pore.viscosity',
                            throat_viscosity='throat.viscosity',
                            model=flow, regen_mode='normal')

        current = op.models.physics.ionic_conductance.electroneutrality
        self.phys.add_model(propname='throat.ionic_conductance',
                            ions=[self.Na.name, self.Cl.name],
                            model=current, regen_mode='normal')

        eA_dif = op.models.physics.diffusive_conductance.ordinary_diffusion
        self.phys.add_model(propname='throat.diffusive_conductance.'
                            + self.Na.name,
                            pore_diffusivity='pore.diffusivity.'+self.Na.name,
                            throat_diffusivity='throat.diffusivity.'
                            + self.Na.name, model=eA_dif, regen_mode='normal')

        eB_dif = op.models.physics.diffusive_conductance.ordinary_diffusion
        self.phys.add_model(propname='throat.diffusive_conductance.'
                            + self.Cl.name,
                            pore_diffusivity='pore.diffusivity.'+self.Cl.name,
                            throat_diffusivity='throat.diffusivity.'
                            + self.Cl.name, model=eB_dif, regen_mode='normal')

        # settings for algorithms
        self.settings1 = {'solver_maxiter': 5, 'solver_tol': 1e-08,
                          'solver_rtol': 1e-08, 'max_iter': 10}
        self.settings2 = {'g_tol': 1e-4, 'g_max_iter': 4, 't_output': 5000,
                          't_step': 500, 't_final': 20000,
                          't_scheme': 'implicit'}

    def test_transient_ionic_reactive_transport(self):
        # algorithms
        sf = op.algorithms.StokesFlow(network=self.net, phase=self.phase,
                                      settings=self.settings1)
        sf.set_value_BC(pores=self.net.pores('back'), values=0.01)
        sf.set_value_BC(pores=self.net.pores('front'), values=0.00)
        sf.run()
        self.phase.update(sf.results())

        p = op.algorithms.TransientChargeConservation(network=self.net,
                                                      phase=self.phase,
                                                      settings=self.settings1)
        p.set_value_BC(pores=self.net.pores('left'), values=0.1)
        p.set_value_BC(pores=self.net.pores('right'), values=0.00)
        p.settings['charge_conservation'] = 'electroneutrality'

        eA = op.algorithms.TransientNernstPlanck(network=self.net,
                                                 phase=self.phase,
                                                 ion=self.Na.name,
                                                 settings=self.settings1)
        eA.set_value_BC(pores=self.net.pores('back'), values=100)
        eA.set_value_BC(pores=self.net.pores('front'), values=90)

        eB = op.algorithms.TransientNernstPlanck(network=self.net,
                                                 phase=self.phase,
                                                 ion=self.Cl.name,
                                                 settings=self.settings1)
        eB.set_value_BC(pores=self.net.pores('back'), values=100)
        eB.set_value_BC(pores=self.net.pores('front'), values=90)

        ad_dif_mig_Na = op.models.physics.ad_dif_mig_conductance.ad_dif_mig
        self.phys.add_model(propname='throat.ad_dif_mig_conductance.'
                            + self.Na.name,
                            pore_pressure=sf.settings['quantity'],
                            model=ad_dif_mig_Na, ion=self.Na.name,
                            s_scheme='powerlaw')

        ad_dif_mig_Cl = op.models.physics.ad_dif_mig_conductance.ad_dif_mig
        self.phys.add_model(propname='throat.ad_dif_mig_conductance.'
                            + self.Cl.name,
                            pore_pressure=sf.settings['quantity'],
                            model=ad_dif_mig_Cl, ion=self.Cl.name,
                            s_scheme='powerlaw')

        it = op.algorithms.TransientIonicTransport(network=self.net,
                                                   phase=self.phase,
                                                   settings=self.settings2)
        it.setup(potential_field=p.name, ions=[eA.name, eB.name])
        it.run()

        self.phase.update(sf.results())
        self.phase.update(p.results())
        self.phase.update(eA.results())
        self.phase.update(eB.results())

        x = ([8.571000e-02, 7.143000e-02, 5.714000e-02, 4.286000e-02,
              2.857000e-02, 1.429000e-02, 1.000000e-01, 8.571000e-02,
              7.143000e-02, 5.714000e-02, 4.286000e-02, 2.857000e-02,
              1.429000e-02, 0.000000e+00, 1.000000e-01, 8.571000e-02,
              7.143000e-02, 5.714000e-02, 4.286000e-02, 2.857000e-02,
              1.429000e-02, 0.000000e+00, 1.000000e-01, 8.571000e-02,
              7.143000e-02, 5.714000e-02, 4.286000e-02, 2.857000e-02,
              1.429000e-02, 0.000000e+00, 1.000000e-01, 8.571000e-02,
              7.143000e-02, 5.714000e-02, 4.286000e-02, 2.857000e-02,
              1.429000e-02, 0.000000e+00, 1.000000e-01, 8.571000e-02,
              7.143000e-02, 5.714000e-02, 4.286000e-02, 2.857000e-02,
              1.429000e-02, 0.000000e+00, 1.000000e-01, 8.571000e-02,
              7.143000e-02, 5.714000e-02, 4.286000e-02, 2.857000e-02,
              1.429000e-02, 0.000000e+00, 8.571000e-02, 7.143000e-02,
              5.714000e-02, 4.286000e-02, 2.857000e-02, 1.429000e-02,
              9.000000e+01, 9.000000e+01, 9.000000e+01, 9.000000e+01,
              9.000000e+01, 9.000000e+01, 9.343697e+01, 9.343697e+01,
              9.343697e+01, 9.343697e+01, 9.343697e+01, 9.343697e+01,
              9.343697e+01, 9.343697e+01, 9.577144e+01, 9.577145e+01,
              9.577145e+01, 9.577145e+01, 9.577145e+01, 9.577145e+01,
              9.577145e+01, 9.577144e+01, 9.735708e+01, 9.735709e+01,
              9.735709e+01, 9.735709e+01, 9.735709e+01, 9.735709e+01,
              9.735709e+01, 9.735708e+01, 9.843409e+01, 9.843409e+01,
              9.843410e+01, 9.843410e+01, 9.843410e+01, 9.843410e+01,
              9.843409e+01, 9.843409e+01, 9.916563e+01, 9.916563e+01,
              9.916563e+01, 9.916563e+01, 9.916563e+01, 9.916563e+01,
              9.916563e+01, 9.916563e+01, 9.966251e+01, 9.966251e+01,
              9.966251e+01, 9.966251e+01, 9.966251e+01, 9.966251e+01,
              9.966251e+01, 9.966251e+01, 1.000000e+02, 1.000000e+02,
              1.000000e+02, 1.000000e+02, 1.000000e+02, 1.000000e+02,
              9.000000e+01, 9.000000e+01, 9.000000e+01, 9.000000e+01,
              9.000000e+01, 9.000000e+01, 9.269748e+01, 9.269748e+01,
              9.269748e+01, 9.269748e+01, 9.269748e+01, 9.269748e+01,
              9.269748e+01, 9.269748e+01, 9.479053e+01, 9.479054e+01,
              9.479054e+01, 9.479054e+01, 9.479054e+01, 9.479054e+01,
              9.479054e+01, 9.479053e+01, 9.641461e+01, 9.641461e+01,
              9.641461e+01, 9.641461e+01, 9.641461e+01, 9.641461e+01,
              9.641461e+01, 9.641461e+01, 9.767477e+01, 9.767478e+01,
              9.767478e+01, 9.767478e+01, 9.767478e+01, 9.767478e+01,
              9.767478e+01, 9.767477e+01, 9.865258e+01, 9.865258e+01,
              9.865258e+01, 9.865258e+01, 9.865258e+01, 9.865258e+01,
              9.865258e+01, 9.865258e+01, 9.941129e+01, 9.941129e+01,
              9.941129e+01, 9.941129e+01, 9.941129e+01, 9.941129e+01,
              9.941129e+01, 9.941129e+01, 1.000000e+02, 1.000000e+02,
              1.000000e+02, 1.000000e+02, 1.000000e+02, 1.000000e+02])
        y1 = np.around(p[p.settings['quantity']], decimals=5)
        y2 = np.around(eA[eA.settings['quantity']], decimals=5)
        y3 = np.around(eB[eB.settings['quantity']], decimals=5)
        y = np.concatenate((y1, y2, y3))
        times = ['pore.concentration.Na_mix_01@5000',
                 'pore.concentration.Cl_mix_01@5000', 'pore.potential@5000',
                 'pore.concentration.Na_mix_01@10000',
                 'pore.concentration.Cl_mix_01@10000', 'pore.potential@10000',
                 'pore.concentration.Na_mix_01@15000',
                 'pore.concentration.Cl_mix_01@15000', 'pore.potential@15000',
                 'pore.concentration.Na_mix_01@19500',
                 'pore.concentration.Cl_mix_01@19500', 'pore.potential@19500']
        assert np.all(x == y)
        assert (set(times).issubset(set(self.phase.keys())))

    def teardown_class(self):
        ws = op.Workspace()
        ws.clear()


if __name__ == '__main__':

    t = TransientIonicTransportTest()
    t.setup_class()
    self = t
    for item in t.__dir__():
        if item.startswith('test'):
            print('running test: '+item)
            t.__getattribute__(item)()
