# -*- coding: utf-8 -*-

from odoo.addons.stock.tests.common2 import TestStockCommon


class TestInventory(TestStockCommon):

    def test_inventory_product(self):
        # TDE NOTE: replaces test/inventory.yml present until saas-10
        inventory = self.env['stock.inventory'].sudo(self.user_stock_manager).create({
            'name': 'Starting for product_1',
            'filter': 'product',
            'location_id': self.warehouse_1.lot_stock_id.id,
            'product_id': self.product_1.id,
        })
        inventory.prepare_inventory()

        # As done in common.py, there is already an inventory line existing
        self.assertEqual(len(inventory.line_ids), 1)
        self.assertEqual(inventory.line_ids.theoretical_qty, 50.0)
        self.assertEqual(inventory.line_ids.product_id, self.product_1)
        self.assertEqual(inventory.line_ids.product_uom_id, self.uom_unit)

        # Update the line, set to 35
        inventory.line_ids.write({'product_qty': 35.0})
        inventory.action_done()

        # Check related move and quants
        self.assertIn(inventory.name, inventory.move_ids.name)
        self.assertEqual(inventory.move_ids.product_qty, 15.0)
        self.assertEqual(inventory.move_ids.location_id, self.warehouse_1.lot_stock_id)
        self.assertEqual(inventory.move_ids.location_dest_id, self.env.ref('stock.location_inventory'))  # Inventory loss
        self.assertEqual(inventory.move_ids.state, 'done')
        self.assertEqual(inventory.move_ids.quant_ids.location_id, self.env.ref('stock.location_inventory'))  # Inventory loss
        self.assertEqual(inventory.move_ids.quant_ids.qty, 15.0)
        self.assertEqual(inventory.move_ids.quant_ids.history_ids[0].product_qty, 50.0)

        # Check quantity of product in various locations: current, its parent, brother and other
        self.assertEqual(self.product_1.with_context(location=self.warehouse_1.lot_stock_id.id).qty_available, 35.0)
        self.assertEqual(self.product_1.with_context(location=self.warehouse_1.lot_stock_id.location_id.id).qty_available, 35.0)
        self.assertEqual(self.product_1.with_context(location=self.warehouse_1.view_location_id.id).qty_available, 35.0)
        self.assertEqual(self.product_1.with_context(location=self.warehouse_1.wh_input_stock_loc_id.id).qty_available, 0.0)
        self.assertEqual(self.product_1.with_context(location=self.env.ref('stock.stock_location_stock').id).qty_available, 0.0)

    def test_inventory_wizard(self):
        # Check inventory performed in setup was effectivley performed
        self.assertEqual(self.product_1.virtual_available, 50.0)
        self.assertEqual(self.product_1.qty_available, 50.0)

        # Check inventory obj details (1 inventory with 1 line, because 1 product change)
        inventory = self.env['stock.inventory'].search([('id', 'not in', self.existing_inventories.ids)])
        self.assertEqual(len(inventory), 1)
        self.assertIn('INV: %s' % self.product_1.name, inventory.name)
        self.assertEqual(len(inventory.line_ids), 1)
        self.assertEqual(inventory.line_ids.product_id, self.product_1)
        self.assertEqual(inventory.line_ids.product_qty, 50.0)

        # Check associated quants: 1 quant for the product and the quantity
        quant = self.env['stock.quant'].search([('id', 'not in', self.existing_quants.ids)])
        self.assertEqual(len(quant), 1)
        # print quant.name, quant.product_id, quant.location_id
        # TDE TODO: expand this test

    def test_basic_move(self):
        # TDE NOTE: replaces test/move.yml present until saas-10, including onchanges
        Move = self.env['stock.move'].sudo(self.user_stock_manager)
        product = self.product_3.sudo(self.user_stock_manager)

        # simulate create + onchange
        customer_move = self._create_move(product, self.warehouse_1.lot_stock_id, self.env.ref('stock.stock_location_customers'), product_uom_qty=5)

        # test move values
        self.assertEqual(customer_move.product_uom, self.uom_kunit)
        self.assertEqual(customer_move.location_id, self.warehouse_1.lot_stock_id)
        self.assertEqual(customer_move.location_dest_id, self.env.ref('stock.stock_location_customers'))

        # confirm move, check quantity on hand and virtually available, without location context
        customer_move.action_confirm()
        self.assertEqual(product.qty_available, 0.0)
        self.assertEqual(product.virtual_available, -5.0)

        customer_move.action_done()
        self.assertEqual(product.qty_available, -5.0)
        self.assertEqual(product.with_context(location=self.env.ref('stock.stock_location_customers').id).qty_available, 5.0)

        # compensate negative quants by receiving products from supplier
        receive_move = self._create_move(product, self.env.ref('stock.stock_location_suppliers'), self.warehouse_1.lot_stock_id, product_uom_qty=15)

        receive_move.action_confirm()
        receive_move.action_done()

        self.assertEqual(product.qty_available, 10.0)
        self.assertEqual(product.virtual_available, 10.0)

        # new move towards customer
        customer_move_2 = self._create_move(product, self.warehouse_1.lot_stock_id, self.env.ref('stock.stock_location_customers'), product_uom_qty=2)

        customer_move_2.action_confirm()
        self.assertEqual(product.qty_available, 10.0)
        self.assertEqual(product.virtual_available, 8.0)

        customer_move_2.action_done()
        self.assertEqual(product.qty_available, 8.0)
        self.assertEqual(product.with_context(location=self.env.ref('stock.stock_location_customers').id).qty_available, 7.0)

    def test_inventory_adjustment_and_negative_quants_1(self):
        """Make sure negative quants from returns get wiped out with an inventory adjustment"""
        productA = self.env['product.product'].create({'name': 'Product A', 'type': 'product'})
        stock_location = self.env.ref('stock.stock_location_stock')
        customer_location = self.env.ref('stock.stock_location_customers')
        location_loss = self.env.ref('stock.location_inventory')

        # Create a picking out and force availability
        picking_out = self.env['stock.picking'].create({
            'partner_id': self.env.ref('base.res_partner_2').id,
            'picking_type_id': self.env.ref('stock.picking_type_out').id,
            'location_id': stock_location.id,
            'location_dest_id': customer_location.id,
        })
        self.env['stock.move'].create({
            'name': productA.name,
            'product_id': productA.id,
            'product_uom_qty': 1,
            'product_uom': productA.uom_id.id,
            'picking_id': picking_out.id,
            'location_id': stock_location.id,
            'location_dest_id': customer_location.id,
        })
        picking_out.action_confirm()
        picking_out.force_assign()
        picking_out.do_transfer()

        # Create return picking for all goods
        default_data = self.env['stock.return.picking']\
            .with_context(active_ids=picking_out.ids, active_id=picking_out.ids[0])\
            .default_get([
                'move_dest_exists',
                'original_location_id',
                'product_return_moves',
                'parent_location_id',
                'location_id',
            ])
        return_wiz = self.env['stock.return.picking']\
            .with_context(active_ids=picking_out.ids, active_id=picking_out.ids[0])\
            .create(default_data)
        res = return_wiz.create_returns()
        return_pick = self.env['stock.picking'].browse(res['res_id'])
        return_pick.action_assign()
        return_pick.do_transfer()

        # Make an inventory adjustment to set the quantity to 0
        inventory = self.env['stock.inventory'].create({
            'name': 'Starting for product_1',
            'filter': 'product',
            'location_id': stock_location.id,
            'product_id': productA.id,
        })
        inventory.prepare_inventory()
        self.assertEqual(len(inventory.line_ids), 1, "Wrong inventory lines generated.")
        self.assertEqual(inventory.line_ids.theoretical_qty, 0, "Theoretical quantity should be zero.")
        inventory.action_done()

        # The inventory adjustment should have created two moves
        self.assertEqual(len(inventory.move_ids), 2)
        quantity = inventory.move_ids.mapped('product_qty')
        self.assertEqual(quantity, [1, 1], "Moves created with wrong quantity.")
        location_ids = inventory.move_ids.mapped('location_id').ids
        self.assertEqual(set(location_ids), {stock_location.id, location_loss.id})

        # There should be no quant in the stock location
        quants = self.env['stock.quant'].search([('product_id', '=', productA.id), ('location_id', '=', stock_location.id)])
        self.assertEqual(len(quants), 0)

        # There should be one quant in the inventory loss location
        quant = self.env['stock.quant'].search([('product_id', '=', productA.id), ('location_id', '=', location_loss.id)])
        self.assertEqual(len(quant), 1)
        self.assertEqual(quant.qty, 1)

    def test_inventory_adjustment_and_negative_quants_2(self):
        """Make sure negative quants get wiped out with an inventory adjustment"""
        productA = self.env['product.product'].create({'name': 'Product A', 'type': 'product'})
        stock_location = self.env.ref('stock.stock_location_stock')
        customer_location = self.env.ref('stock.stock_location_customers')
        location_loss = self.env.ref('stock.location_inventory')

        # Create a picking out and force availability
        picking_out = self.env['stock.picking'].create({
            'partner_id': self.env.ref('base.res_partner_2').id,
            'picking_type_id': self.env.ref('stock.picking_type_out').id,
            'location_id': stock_location.id,
            'location_dest_id': customer_location.id,
        })
        self.env['stock.move'].create({
            'name': productA.name,
            'product_id': productA.id,
            'product_uom_qty': 1,
            'product_uom': productA.uom_id.id,
            'picking_id': picking_out.id,
            'location_id': stock_location.id,
            'location_dest_id': customer_location.id,
        })
        picking_out.action_confirm()
        picking_out.force_assign()
        picking_out.do_transfer()

        # Make an inventory adjustment to set the quantity to 0
        inventory = self.env['stock.inventory'].create({
            'name': 'Starting for product_1',
            'filter': 'product',
            'location_id': stock_location.id,
            'product_id': productA.id,
        })
        inventory.prepare_inventory()
        self.assertEqual(len(inventory.line_ids), 1, "Wrong inventory lines generated.")
        self.assertEqual(inventory.line_ids.theoretical_qty, -1, "Theoretical quantity should be -1.")
        inventory.line_ids.product_qty = 0  # Put the quantity back to 0
        inventory.action_done()

        # The inventory adjustment should have created one
        self.assertEqual(len(inventory.move_ids), 1)
        quantity = inventory.move_ids.mapped('product_qty')
        self.assertEqual(quantity, [1], "Moves created with wrong quantity.")
        location_ids = inventory.move_ids.mapped('location_id').ids
        self.assertEqual(set(location_ids), {location_loss.id})

        # There should be no quant in the stock location
        quants = self.env['stock.quant'].search([('product_id', '=', productA.id), ('location_id', '=', stock_location.id)])
        self.assertEqual(len(quants), 0)

        # There should be no quant in the inventory loss location
        quant = self.env['stock.quant'].search([('product_id', '=', productA.id), ('location_id', '=', location_loss.id)])
        self.assertEqual(len(quant), 0)


class TestResupply(TestStockCommon):
    def setUp(self):
        super(TestResupply, self).setUp()

        self.warehouse_2 = self.env['stock.warehouse'].create({
            'name': 'Small Warehouse',
            'code': 'SWH',
            'default_resupply_wh_id': self.warehouse_1.id,
            'resupply_wh_ids': [(6, 0, [self.warehouse_1.id])]
        })

        # minimum stock rule for test product on this warehouse
        self.env['stock.warehouse.orderpoint'].create({
            'warehouse_id': self.warehouse_2.id,
            'location_id': self.warehouse_2.lot_stock_id.id,
            'product_id': self.product_1.id,
            'product_min_qty': 10,
            'product_max_qty': 100,
            'product_uom': self.uom_unit.id,
        })

    def test_resupply_from_wh(self):
        # TDE NOTE: replaces tests/test_resupply.py, present until saas-10
        OrderScheduler = self.env['procurement.order']
        OrderScheduler.run_scheduler()
        # we generated 2 procurements for product A: one on small wh and the other one on the transit location
        procs = OrderScheduler.search([('product_id', '=', self.product_1.id)])
        self.assertEqual(len(procs), 2)

        proc1 = procs.filtered(lambda order: order.warehouse_id == self.warehouse_2)
        self.assertEqual(proc1.state, 'running')

        proc2 = procs.filtered(lambda order: order.warehouse_id == self.warehouse_1)
        self.assertEqual(proc2.location_id.usage, 'transit')
        self.assertNotEqual(proc2.state, 'exception')

        proc2.run()
        self.assertEqual(proc2.state, 'running')
        self.assertTrue(proc2.rule_id)